import asyncio
import base64
import json

from fastapi.testclient import TestClient
import httpx

from app.main import RegisterRequest, admin_base, app, client_id, map_user, token_from_header, userinfo


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "auth-service"


def test_role_mapping_and_legacy_token_header():
    assert token_from_header("Token abc") == "abc"
    user = map_user({"sub": "1", "preferred_username": "dat", "realm_access": {"roles": ["product-manager"]}})
    assert user["roles"] == ["PRODUCT_MANAGER"]


def test_keycloak_contract_defaults():
    assert client_id() == "aims-app"
    assert admin_base().endswith("/auth")
    assert RegisterRequest(username="buyer", email="buyer@example.test", password="secret123").fullName == ""


def test_userinfo_merges_verified_access_token_roles(monkeypatch):
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "user-1", "realm_access": {"roles": ["ADMIN"]}}).encode()).decode().rstrip("=")
    token = f"{header}.{payload}.signature"

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return httpx.Response(200, json={"sub": "user-1", "preferred_username": "admin"})

    monkeypatch.setattr("app.main.httpx.AsyncClient", Client)
    claims = asyncio.run(userinfo(token))
    assert map_user(claims)["roles"] == ["ADMIN"]
