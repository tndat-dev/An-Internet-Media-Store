"""Keycloak-backed authentication boundary; this service stores no passwords."""

from __future__ import annotations

import base64
import binascii
import json
import os
import secrets
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from app.observability import install_observability


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8)
    fullName: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=30)


class ChangePasswordRequest(BaseModel):
    oldPassword: str = Field(min_length=1)
    newPassword: str = Field(min_length=8)


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


BUSINESS_ROLES = {"CUSTOMER", "PRODUCT_MANAGER", "ADMIN"}


def issuer() -> str:
    return os.getenv(
        "KEYCLOAK_ISSUER",
        "http://keycloak-keycloakx-http.keycloak.svc.cluster.local/auth/realms/aims",
    ).rstrip("/")


def client_id() -> str:
    return os.getenv("KEYCLOAK_CLIENT_ID", "aims-app")


def admin_base() -> str:
    return issuer().split("/realms/", 1)[0]


def token_from_header(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing access token")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() not in {"bearer", "token"} or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    return token


def map_user(claims: dict[str, Any]) -> dict[str, Any]:
    realm_roles = claims.get("realm_access", {}).get("roles", [])
    mapped = []
    for role in realm_roles:
        normalized = str(role).upper().replace("-", "_")
        if normalized in {"CUSTOMER", "PRODUCT_MANAGER", "ADMIN"}:
            mapped.append(normalized)
    return {
        "userId": claims.get("sub", ""),
        "username": claims.get("preferred_username", claims.get("email", "")),
        "email": claims.get("email", ""),
        "status": "ACTIVE",
        "roles": mapped or ["CUSTOMER"],
    }


async def userinfo(token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{issuer()}/protocol/openid-connect/userinfo", headers={"Authorization": f"Bearer {token}"})
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    verified = response.json()
    # Keycloak verifies signature, issuer, expiration and session before this
    # point. Some realms omit realm_access from the userinfo response even
    # though it is present in the already-verified access token. Merge only
    # role claims whose subject matches the verified userinfo subject.
    try:
        encoded = token.split(".")[1]
        encoded += "=" * (-len(encoded) % 4)
        access_claims = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
        if access_claims.get("sub") == verified.get("sub"):
            verified["realm_access"] = access_claims.get("realm_access", {})
    except (IndexError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        pass
    return verified


async def token_request(username: str, password: str) -> dict[str, Any]:
    data = {
        "grant_type": "password",
        "client_id": client_id(),
        "username": username,
        "password": password,
        "scope": "openid profile email roles",
    }
    client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=10) as client:
        result = await client.post(f"{issuer()}/protocol/openid-connect/token", data=data)
    if result.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result.json()


async def admin_token() -> str:
    client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
    if not client_secret:
        raise HTTPException(status_code=503, detail="Keycloak client credential is unavailable")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{issuer()}/protocol/openid-connect/token",
            data={"grant_type": "client_credentials", "client_id": client_id(), "client_secret": client_secret},
        )
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Keycloak administration is unavailable")
    return response.json()["access_token"]


async def require_admin(authorization: str | None) -> dict[str, Any]:
    claims = await userinfo(token_from_header(authorization))
    if "ADMIN" not in map_user(claims)["roles"]:
        raise HTTPException(status_code=403, detail="Administrator role is required")
    return claims


async def realm_role(client: httpx.AsyncClient, token: str, name: str) -> dict[str, Any]:
    response = await client.get(f"{admin_base()}/admin/realms/aims/roles/{name}", headers={"Authorization": f"Bearer {token}"})
    if response.status_code != 200:
        raise HTTPException(status_code=422, detail=f"Unknown role: {name}")
    return response.json()


async def admin_user_view(client: httpx.AsyncClient, token: str, representation: dict[str, Any]) -> dict[str, Any]:
    user_id = representation["id"]
    roles_response = await client.get(f"{admin_base()}/admin/realms/aims/users/{user_id}/role-mappings/realm", headers={"Authorization": f"Bearer {token}"})
    roles = [role["name"] for role in roles_response.json() if role.get("name") in BUSINESS_ROLES] if roles_response.status_code == 200 else []
    attributes = representation.get("attributes") or {}
    status = (attributes.get("aimsStatus") or ["ACTIVE" if representation.get("enabled", False) else "DEACTIVATED"])[0]
    full_name = " ".join(filter(None, [representation.get("firstName", ""), representation.get("lastName", "")])).strip()
    return {
        "userId": user_id,
        "username": representation.get("username", ""),
        "email": representation.get("email", ""),
        "fullName": full_name,
        "phone": (attributes.get("phone") or [""])[0],
        "status": status,
        "roles": roles,
        "createdAt": representation.get("createdTimestamp", 0),
        "lastLogin": None,
    }


app = FastAPI(title="AIMS auth-service", version="1.0.0")
install_observability(app)


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "auth-service", "issuer": issuer()}


@app.get("/api/auth/config/")
async def oidc_config() -> dict[str, str]:
    return {"issuer": issuer(), "clientId": client_id()}


@app.post("/api/auth/login/")
async def login(payload: LoginRequest) -> dict[str, Any]:
    token = (await token_request(payload.username, payload.password))["access_token"]
    return {"token": token, "user": map_user(await userinfo(token))}


@app.get("/api/auth/me/")
async def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return map_user(await userinfo(token_from_header(authorization)))


@app.post("/api/auth/logout/", status_code=204)
async def logout() -> Response:
    return Response(status_code=204)


@app.post("/api/auth/register/")
async def register(payload: RegisterRequest) -> dict[str, Any]:
    token = await admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    names = payload.fullName.strip().split(" ", 1)
    representation = {
        "username": payload.username,
        "email": payload.email,
        "enabled": True,
        "emailVerified": False,
        "firstName": names[0] if names else "",
        "lastName": names[1] if len(names) > 1 else "",
        "attributes": {"phone": [payload.phone]} if payload.phone else {},
        "credentials": [{"type": "password", "value": payload.password, "temporary": False}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        created = await client.post(f"{admin_base()}/admin/realms/aims/users", json=representation, headers=headers)
        if created.status_code == 409:
            raise HTTPException(status_code=400, detail="Username or email already exists")
        if created.status_code != 201:
            raise HTTPException(status_code=503, detail="Keycloak could not create the account")
        user_id = created.headers["location"].rstrip("/").rsplit("/", 1)[-1]
        role = await client.get(f"{admin_base()}/admin/realms/aims/roles/CUSTOMER", headers=headers)
        if role.status_code != 200:
            raise HTTPException(status_code=503, detail="Keycloak CUSTOMER role is unavailable")
        assigned = await client.post(
            f"{admin_base()}/admin/realms/aims/users/{user_id}/role-mappings/realm",
            json=[role.json()],
            headers=headers,
        )
        if assigned.status_code != 204:
            raise HTTPException(status_code=503, detail="Keycloak could not assign the customer role")
    return await login(LoginRequest(username=payload.username, password=payload.password))


@app.post("/api/auth/change-password/", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    access_token = token_from_header(authorization)
    claims = await userinfo(access_token)
    await token_request(str(claims.get("preferred_username", "")), payload.oldPassword)
    token = await admin_token()
    user_id = str(claims.get("sub", ""))
    async with httpx.AsyncClient(timeout=10) as client:
        changed = await client.put(
            f"{admin_base()}/admin/realms/aims/users/{user_id}/reset-password",
            json={"type": "password", "value": payload.newPassword, "temporary": False},
            headers={"Authorization": f"Bearer {token}"},
        )
    if changed.status_code != 204:
        raise HTTPException(status_code=503, detail="Keycloak could not change the password")
    return Response(status_code=204)


@app.get("/api/admin/users/")
async def list_admin_users(
    authorization: str | None = Header(default=None), search: str = "", role: str = "", status: str = "", page: int = 1,
) -> dict[str, Any]:
    await require_admin(authorization)
    token = await admin_token()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{admin_base()}/admin/realms/aims/users",
            params={"search": search, "first": max(0, (page - 1) * 20), "max": 20},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=503, detail="Keycloak users are unavailable")
        users = [await admin_user_view(client, token, item) for item in response.json()]
        count_response = await client.get(f"{admin_base()}/admin/realms/aims/users/count", params={"search": search}, headers={"Authorization": f"Bearer {token}"})
    if role:
        users = [user for user in users if role in user["roles"]]
    if status:
        users = [user for user in users if user["status"] == status]
    count = len(users) if role or status else (count_response.json() if count_response.status_code == 200 else len(users))
    return {"count": count, "next": page + 1 if page * 20 < count else None, "previous": page - 1 if page > 1 else None, "results": users}


@app.post("/api/admin/users/", status_code=201)
async def create_admin_user(payload: AdminCreateUserRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    await require_admin(authorization)
    invalid = set(payload.roleNames) - BUSINESS_ROLES
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown roles: {', '.join(sorted(invalid))}")
    token = await admin_token()
    names = payload.fullName.strip().split(" ", 1)
    representation = {"username": payload.username, "email": payload.email, "enabled": True, "emailVerified": False, "firstName": names[0] if names else "", "lastName": names[1] if len(names) > 1 else "", "attributes": {"phone": [payload.phone], "aimsStatus": ["ACTIVE"]}, "credentials": [{"type": "password", "value": secrets.token_urlsafe(18), "temporary": True}], "requiredActions": ["UPDATE_PASSWORD"]}
    async with httpx.AsyncClient(timeout=15) as client:
        created = await client.post(f"{admin_base()}/admin/realms/aims/users", json=representation, headers={"Authorization": f"Bearer {token}"})
        if created.status_code == 409:
            raise HTTPException(status_code=400, detail="Username or email already exists")
        if created.status_code != 201:
            raise HTTPException(status_code=503, detail="Keycloak could not create the user")
        user_id = created.headers["location"].rstrip("/").rsplit("/", 1)[-1]
        roles = [await realm_role(client, token, name) for name in payload.roleNames]
        if roles:
            await client.post(f"{admin_base()}/admin/realms/aims/users/{user_id}/role-mappings/realm", json=roles, headers={"Authorization": f"Bearer {token}"})
        result = await client.get(f"{admin_base()}/admin/realms/aims/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
        return await admin_user_view(client, token, result.json())


@app.post("/api/admin/users/{user_id}/roles/")
async def set_admin_roles(user_id: str, payload: AdminRolesRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    await require_admin(authorization)
    invalid = set(payload.roleNames) - BUSINESS_ROLES
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown roles: {', '.join(sorted(invalid))}")
    token = await admin_token()
    async with httpx.AsyncClient(timeout=15) as client:
        current = await client.get(f"{admin_base()}/admin/realms/aims/users/{user_id}/role-mappings/realm", headers={"Authorization": f"Bearer {token}"})
        business_current = [role for role in current.json() if role.get("name") in BUSINESS_ROLES]
        if business_current:
            await client.request("DELETE", f"{admin_base()}/admin/realms/aims/users/{user_id}/role-mappings/realm", json=business_current, headers={"Authorization": f"Bearer {token}"})
        desired = [await realm_role(client, token, name) for name in payload.roleNames]
        if desired:
            await client.post(f"{admin_base()}/admin/realms/aims/users/{user_id}/role-mappings/realm", json=desired, headers={"Authorization": f"Bearer {token}"})
        result = await client.get(f"{admin_base()}/admin/realms/aims/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
        if result.status_code != 200:
            raise HTTPException(status_code=404, detail="User not found")
        return await admin_user_view(client, token, result.json())


@app.post("/api/admin/users/{user_id}/status/")
async def set_admin_status(user_id: str, payload: AdminStatusRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    await require_admin(authorization)
    status = payload.status.upper()
    if status not in {"ACTIVE", "DEACTIVATED", "BLOCKED"}:
        raise HTTPException(status_code=422, detail="Invalid account status")
    token = await admin_token()
    async with httpx.AsyncClient(timeout=15) as client:
        result = await client.get(f"{admin_base()}/admin/realms/aims/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
        if result.status_code != 200:
            raise HTTPException(status_code=404, detail="User not found")
        representation = result.json()
        attributes = representation.get("attributes") or {}
        attributes["aimsStatus"] = [status]
        representation.update({"enabled": status == "ACTIVE", "attributes": attributes})
        updated = await client.put(f"{admin_base()}/admin/realms/aims/users/{user_id}", json=representation, headers={"Authorization": f"Bearer {token}"})
        if updated.status_code != 204:
            raise HTTPException(status_code=503, detail="Keycloak could not update the user")
        representation["attributes"] = attributes
        return await admin_user_view(client, token, representation)


@app.post("/api/admin/users/{user_id}/reset-password/", status_code=204)
async def reset_admin_password(user_id: str, authorization: str | None = Header(default=None)) -> Response:
    await require_admin(authorization)
    token = await admin_token()
    async with httpx.AsyncClient(timeout=15) as client:
        result = await client.get(f"{admin_base()}/admin/realms/aims/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
        if result.status_code != 200:
            raise HTTPException(status_code=404, detail="User not found")
        representation = result.json()
        required = set(representation.get("requiredActions") or [])
        required.add("UPDATE_PASSWORD")
        representation["requiredActions"] = sorted(required)
        updated = await client.put(f"{admin_base()}/admin/realms/aims/users/{user_id}", json=representation, headers={"Authorization": f"Bearer {token}"})
        if updated.status_code != 204:
            raise HTTPException(status_code=503, detail="Keycloak could not start password reset")
    return Response(status_code=204)


@app.get("/api/admin/roles/")
async def list_admin_roles(authorization: str | None = Header(default=None)) -> list[dict[str, str]]:
    await require_admin(authorization)
    token = await admin_token()
    async with httpx.AsyncClient(timeout=15) as client:
        roles = [await realm_role(client, token, name) for name in sorted(BUSINESS_ROLES)]
    return [{"roleId": role["id"], "roleName": role["name"], "description": role.get("description", "")} for role in roles]
