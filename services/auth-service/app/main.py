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


def issuer() -> str:
    return os.getenv("KEYCLOAK_ISSUER", "http://keycloak.production.svc.cluster.local:8080/realms/aims").rstrip("/")


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


app = FastAPI(title="AIMS auth-service", version="1.0.0")


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "auth-service", "issuer": issuer()}


@app.get("/api/auth/config/")
async def oidc_config() -> dict[str, str]:
    return {"issuer": issuer(), "clientId": os.getenv("KEYCLOAK_CLIENT_ID", "aims-web")}


@app.post("/api/auth/login/")
async def login(payload: LoginRequest) -> dict[str, Any]:
    data = {
        "grant_type": "password",
        "client_id": os.getenv("KEYCLOAK_CLIENT_ID", "aims-web"),
        "username": payload.username,
        "password": payload.password,
        "scope": "openid profile email",
    }
    client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=10) as client:
        result = await client.post(f"{issuer()}/protocol/openid-connect/token", data=data)
    if result.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = result.json()["access_token"]
    return {"token": token, "user": map_user(await userinfo(token))}


@app.get("/api/auth/me/")
async def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return map_user(await userinfo(token_from_header(authorization)))


@app.post("/api/auth/logout/", status_code=204)
async def logout() -> Response:
    return Response(status_code=204)


@app.post("/api/auth/register/")
async def register_disabled() -> None:
    raise HTTPException(status_code=501, detail="Registration is managed by Keycloak self-service")
