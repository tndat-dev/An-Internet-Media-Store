"""PostgreSQL-backed authentication and user administration for AIMS."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from fastapi import FastAPI, Header, HTTPException, Response
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.observability import install_observability


BUSINESS_ROLES = {"CUSTOMER", "PRODUCT_MANAGER", "ADMIN"}
PAGE_SIZE = 20
SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS auth_service;
CREATE TABLE IF NOT EXISTS auth_service.users (
  user_id uuid PRIMARY KEY,
  username text NOT NULL,
  email text NOT NULL,
  password_hash text NOT NULL,
  full_name text NOT NULL DEFAULT '',
  phone text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE', 'DEACTIVATED', 'BLOCKED')),
  roles text[] NOT NULL DEFAULT ARRAY['CUSTOMER']::text[],
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  last_login timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS auth_users_username_ci
  ON auth_service.users (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS auth_users_email_ci
  ON auth_service.users (lower(email));
CREATE TABLE IF NOT EXISTS auth_service.tokens (
  token_hash text PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth_service.users(user_id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS auth_tokens_user ON auth_service.tokens(user_id);
CREATE INDEX IF NOT EXISTS auth_tokens_expiry ON auth_service.tokens(expires_at);
"""


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=1024)
    fullName: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=30)


class ChangePasswordRequest(BaseModel):
    oldPassword: str = Field(min_length=1, max_length=1024)
    newPassword: str = Field(min_length=8, max_length=1024)


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    fullName: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=30)
    roleNames: list[str] = Field(default_factory=list)


class AdminRolesRequest(BaseModel):
    roleNames: list[str]


class AdminStatusRequest(BaseModel):
    status: str


def database_url() -> str:
    return os.getenv("AUTH_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()


def token_ttl() -> timedelta:
    try:
        hours = max(1, int(os.getenv("AUTH_TOKEN_TTL_HOURS", "168")))
    except ValueError:
        hours = 168
    return timedelta(hours=hours)


def token_from_header(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing access token")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() not in {"bearer", "token"} or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    return token


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$%s$%s" % (
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(digest).decode(),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_value, expected_value = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode())
        expected = base64.urlsafe_b64decode(expected_value.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def user_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": str(row["user_id"]),
        "username": row["username"],
        "email": row["email"],
        "fullName": row.get("full_name", ""),
        "phone": row.get("phone", ""),
        "status": row["status"],
        "roles": list(row.get("roles") or ["CUSTOMER"]),
        "createdAt": row["created_at"].isoformat() if row.get("created_at") else None,
        "lastLogin": row["last_login"].isoformat() if row.get("last_login") else None,
    }


async def get_connection() -> psycopg.AsyncConnection[Any]:
    url = database_url()
    if not url:
        raise HTTPException(status_code=503, detail="Authentication database is not configured")
    return await psycopg.AsyncConnection.connect(url, row_factory=dict_row)


async def issue_token(connection: psycopg.AsyncConnection[Any], user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    await connection.execute(
        "INSERT INTO auth_service.tokens(token_hash,user_id,expires_at) VALUES (%s,%s,%s)",
        (token_digest(token), user_id, datetime.now(timezone.utc) + token_ttl()),
    )
    return token


async def authenticated_user(authorization: str | None) -> tuple[dict[str, Any], str]:
    token = token_from_header(authorization)
    async with await get_connection() as connection:
        cursor = await connection.execute(
            """SELECT u.* FROM auth_service.tokens t
            JOIN auth_service.users u ON u.user_id=t.user_id
            WHERE t.token_hash=%s AND t.expires_at > now() AND u.status='ACTIVE'""",
            (token_digest(token),),
        )
        row = await cursor.fetchone()
        await connection.execute("DELETE FROM auth_service.tokens WHERE expires_at <= now()")
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    return row, token


async def require_admin(authorization: str | None) -> dict[str, Any]:
    user, _ = await authenticated_user(authorization)
    if "ADMIN" not in (user.get("roles") or []):
        raise HTTPException(status_code=403, detail="Administrator role is required")
    return user


database_ready = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    global database_ready
    url = database_url()
    if not url:
        database_ready = False
        yield
        return
    async with await psycopg.AsyncConnection.connect(url) as connection:
        await connection.execute("SELECT pg_advisory_xact_lock(hashtext('aims-auth-schema-v1'))")
        await connection.execute(SCHEMA_SQL)
    database_ready = True
    yield


app = FastAPI(title="AIMS auth-service", version="2.0.0", lifespan=lifespan)
install_observability(app)


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, Any]:
    return {"status": "ok" if database_ready else "degraded", "service": "auth-service", "databaseReady": database_ready}


@app.get("/api/auth/config/")
async def auth_config() -> dict[str, str]:
    return {"provider": "database", "issuer": "", "clientId": "aims-web"}


@app.post("/api/auth/register/", status_code=201)
async def register(payload: RegisterRequest) -> dict[str, Any]:
    username = payload.username.strip()
    email = payload.email.strip().lower()
    if not username or "@" not in email:
        raise HTTPException(status_code=422, detail="A valid username and email are required")
    user_id = uuid.uuid4()
    try:
        async with await get_connection() as connection:
            cursor = await connection.execute(
                """INSERT INTO auth_service.users(
                  user_id,username,email,password_hash,full_name,phone,roles
                ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (user_id, username, email, hash_password(payload.password), payload.fullName.strip(), payload.phone.strip(), ["CUSTOMER"]),
            )
            row = await cursor.fetchone()
            token = await issue_token(connection, user_id)
    except UniqueViolation as exc:
        raise HTTPException(status_code=400, detail="Username or email already exists") from exc
    return {"token": token, "user": user_view(row)}


@app.post("/api/auth/login/")
async def login(payload: LoginRequest) -> dict[str, Any]:
    identity = payload.username.strip()
    async with await get_connection() as connection:
        cursor = await connection.execute(
            "SELECT * FROM auth_service.users WHERE lower(username)=lower(%s) OR lower(email)=lower(%s) LIMIT 1",
            (identity, identity),
        )
        row = await cursor.fetchone()
        if row is None or not verify_password(payload.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if row["status"] != "ACTIVE":
            raise HTTPException(status_code=403, detail="Account is not active")
        now = datetime.now(timezone.utc)
        await connection.execute("UPDATE auth_service.users SET last_login=%s,updated_at=%s WHERE user_id=%s", (now, now, row["user_id"]))
        row["last_login"] = now
        token = await issue_token(connection, row["user_id"])
    return {"token": token, "user": user_view(row)}


@app.get("/api/auth/me/")
async def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    row, _ = await authenticated_user(authorization)
    return user_view(row)


@app.post("/api/auth/logout/", status_code=204)
async def logout(authorization: str | None = Header(default=None)) -> Response:
    token = token_from_header(authorization)
    async with await get_connection() as connection:
        await connection.execute("DELETE FROM auth_service.tokens WHERE token_hash=%s", (token_digest(token),))
    return Response(status_code=204)


@app.post("/api/auth/change-password/")
async def change_password(payload: ChangePasswordRequest, authorization: str | None = Header(default=None)) -> dict[str, str]:
    user, _ = await authenticated_user(authorization)
    if not verify_password(payload.oldPassword, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    async with await get_connection() as connection:
        await connection.execute(
            "UPDATE auth_service.users SET password_hash=%s,updated_at=now() WHERE user_id=%s",
            (hash_password(payload.newPassword), user["user_id"]),
        )
        await connection.execute("DELETE FROM auth_service.tokens WHERE user_id=%s", (user["user_id"],))
        token = await issue_token(connection, user["user_id"])
    return {"token": token}


@app.get("/api/admin/users/")
async def list_admin_users(
    authorization: str | None = Header(default=None), search: str = "", role: str = "", status: str = "", page: int = 1,
) -> dict[str, Any]:
    await require_admin(authorization)
    page = max(1, page)
    conditions: list[str] = []
    parameters: list[Any] = []
    if search:
        conditions.append("(username ILIKE %s OR email ILIKE %s OR full_name ILIKE %s)")
        parameters.extend([f"%{search}%"] * 3)
    if role:
        conditions.append("%s = ANY(roles)")
        parameters.append(role.upper())
    if status:
        conditions.append("status=%s")
        parameters.append(status.upper())
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    async with await get_connection() as connection:
        count_cursor = await connection.execute(f"SELECT count(*) AS count FROM auth_service.users{where}", parameters)
        count = (await count_cursor.fetchone())["count"]
        cursor = await connection.execute(
            f"SELECT * FROM auth_service.users{where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            [*parameters, PAGE_SIZE, (page - 1) * PAGE_SIZE],
        )
        users = await cursor.fetchall()
    return {"count": count, "next": page + 1 if page * PAGE_SIZE < count else None, "previous": page - 1 if page > 1 else None, "results": [user_view(user) for user in users]}


@app.post("/api/admin/users/", status_code=201)
async def create_admin_user(payload: AdminCreateUserRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    await require_admin(authorization)
    roles = sorted(set(role.upper() for role in payload.roleNames) or {"CUSTOMER"})
    invalid = set(roles) - BUSINESS_ROLES
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown roles: {', '.join(sorted(invalid))}")
    user_id = uuid.uuid4()
    temporary_password = secrets.token_urlsafe(18)
    try:
        async with await get_connection() as connection:
            cursor = await connection.execute(
                """INSERT INTO auth_service.users(user_id,username,email,password_hash,full_name,phone,roles)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (user_id, payload.username.strip(), payload.email.strip().lower(), hash_password(temporary_password), payload.fullName.strip(), payload.phone.strip(), roles),
            )
            row = await cursor.fetchone()
    except UniqueViolation as exc:
        raise HTTPException(status_code=400, detail="Username or email already exists") from exc
    result = user_view(row)
    result["temporaryPassword"] = temporary_password
    return result


async def load_user_for_update(connection: psycopg.AsyncConnection[Any], user_id: str) -> dict[str, Any]:
    try:
        parsed_id = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    cursor = await connection.execute("SELECT * FROM auth_service.users WHERE user_id=%s", (parsed_id,))
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return row


@app.post("/api/admin/users/{user_id}/roles/")
async def set_admin_roles(user_id: str, payload: AdminRolesRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    actor = await require_admin(authorization)
    roles = sorted(set(role.upper() for role in payload.roleNames))
    invalid = set(roles) - BUSINESS_ROLES
    if invalid or not roles:
        raise HTTPException(status_code=422, detail="At least one valid role is required")
    if str(actor["user_id"]) == user_id and "ADMIN" not in roles:
        raise HTTPException(status_code=400, detail="You cannot remove your own administrator role")
    async with await get_connection() as connection:
        await load_user_for_update(connection, user_id)
        cursor = await connection.execute(
            "UPDATE auth_service.users SET roles=%s,updated_at=now() WHERE user_id=%s RETURNING *", (roles, uuid.UUID(user_id))
        )
        row = await cursor.fetchone()
    return user_view(row)


@app.post("/api/admin/users/{user_id}/status/")
async def set_admin_status(user_id: str, payload: AdminStatusRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    actor = await require_admin(authorization)
    status = payload.status.upper()
    if status not in {"ACTIVE", "DEACTIVATED", "BLOCKED"}:
        raise HTTPException(status_code=422, detail="Invalid account status")
    if str(actor["user_id"]) == user_id and status != "ACTIVE":
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    async with await get_connection() as connection:
        await load_user_for_update(connection, user_id)
        cursor = await connection.execute(
            "UPDATE auth_service.users SET status=%s,updated_at=now() WHERE user_id=%s RETURNING *", (status, uuid.UUID(user_id))
        )
        row = await cursor.fetchone()
        if status != "ACTIVE":
            await connection.execute("DELETE FROM auth_service.tokens WHERE user_id=%s", (uuid.UUID(user_id),))
    return user_view(row)


@app.post("/api/admin/users/{user_id}/reset-password/")
async def reset_admin_password(user_id: str, authorization: str | None = Header(default=None)) -> dict[str, str]:
    await require_admin(authorization)
    temporary_password = secrets.token_urlsafe(18)
    async with await get_connection() as connection:
        await load_user_for_update(connection, user_id)
        await connection.execute(
            "UPDATE auth_service.users SET password_hash=%s,updated_at=now() WHERE user_id=%s",
            (hash_password(temporary_password), uuid.UUID(user_id)),
        )
        await connection.execute("DELETE FROM auth_service.tokens WHERE user_id=%s", (uuid.UUID(user_id),))
    return {"temporaryPassword": temporary_password}


@app.get("/api/admin/roles/")
async def list_admin_roles(authorization: str | None = Header(default=None)) -> list[dict[str, str]]:
    await require_admin(authorization)
    return [
        {"roleId": role, "roleName": role, "description": description}
        for role, description in (
            ("ADMIN", "Full AIMS administration"),
            ("CUSTOMER", "Store customer"),
            ("PRODUCT_MANAGER", "Catalog and inventory management"),
        )
    ]
