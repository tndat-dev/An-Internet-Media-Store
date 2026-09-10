"""Keycloak-backed authentication boundary; this service stores no passwords."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field


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
    return response.json()


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


app = FastAPI(title="AIMS auth-service", version="1.0.0")


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
