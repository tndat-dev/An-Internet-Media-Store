import pytest
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIClient

from apps.users.models import Role, User, UserRole

pytestmark = pytest.mark.django_db

PASSWORD = "linh12345"


def make_user(username="linh", password=PASSWORD, role_name="PRODUCT_MANAGER", status="ACTIVE"):
    user = User.objects.create(
        username=username,
        email=f"{username}@aims.local",
        password_hash=make_password(password),
        status=status,
    )
    if role_name:
        role, _ = Role.objects.get_or_create(role_name=role_name)
        UserRole.objects.create(user=user, role=role)
    return user


def test_login_success_returns_token_and_roles():
    make_user()
    client = APIClient()

    response = client.post(
        "/api/auth/login/", {"username": "linh", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 200
    assert response.data["token"]
    assert response.data["user"]["username"] == "linh"
    assert "PRODUCT_MANAGER" in response.data["user"]["roles"]


def test_login_accepts_email_or_username():
    make_user(username="linh")  # email linh@aims.local
    client = APIClient()
    by_email = client.post(
        "/api/auth/login/", {"username": "linh@aims.local", "password": PASSWORD}, format="json"
    )
    assert by_email.status_code == 200
    assert by_email.data["user"]["username"] == "linh"


def test_login_rejects_wrong_password():
    make_user()
    client = APIClient()

    response = client.post(
        "/api/auth/login/", {"username": "linh", "password": "wrong"}, format="json"
    )

    assert response.status_code == 400


def test_me_and_logout_flow():
    make_user()
    client = APIClient()
    token = client.post(
        "/api/auth/login/", {"username": "linh", "password": PASSWORD}, format="json"
    ).data["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["username"] == "linh"

    logout = client.post("/api/auth/logout/", {}, format="json")
    assert logout.status_code == 204

    # Token is revoked -> subsequent auth fails.
    assert client.get("/api/auth/me/").status_code == 401


def test_me_requires_authentication():
    assert APIClient().get("/api/auth/me/").status_code == 401


def test_manager_endpoint_allows_manager_and_blocks_others():
    make_user(username="mgr", role_name="PRODUCT_MANAGER")
    make_user(username="plain", role_name=None)
    client = APIClient()

    mgr_token = client.post(
        "/api/auth/login/", {"username": "mgr", "password": PASSWORD}, format="json"
    ).data["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Token {mgr_token}")
    assert client.get("/api/orders/manage/pending/").status_code == 200

    plain_token = client.post(
        "/api/auth/login/", {"username": "plain", "password": PASSWORD}, format="json"
    ).data["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Token {plain_token}")
    assert client.get("/api/orders/manage/pending/").status_code == 403


def test_public_endpoints_stay_open_without_token():
    # No DEFAULT_PERMISSION_CLASSES -> customer/public endpoints remain AllowAny.
    assert APIClient().get("/api/health/").status_code == 200
    assert APIClient().get("/api/products/").status_code == 200


def test_login_sets_last_login():
    make_user()
    client = APIClient()
    client.post("/api/auth/login/", {"username": "linh", "password": PASSWORD}, format="json")
    assert User.objects.get(username="linh").last_login is not None


def test_change_password_rotates_token_and_validates():
    make_user()
    client = APIClient()
    token = client.post(
        "/api/auth/login/", {"username": "linh", "password": PASSWORD}, format="json"
    ).data["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    # wrong old password -> 400
    assert client.post(
        "/api/auth/change-password/", {"oldPassword": "nope", "newPassword": "brandnew123"}, format="json"
    ).status_code == 400
    # new == old -> 400
    assert client.post(
        "/api/auth/change-password/", {"oldPassword": PASSWORD, "newPassword": PASSWORD}, format="json"
    ).status_code == 400

    resp = client.post(
        "/api/auth/change-password/", {"oldPassword": PASSWORD, "newPassword": "brandnew123"}, format="json"
    )
    assert resp.status_code == 200
    new_token = resp.data["token"]
    assert new_token != token

    # old token no longer works; new token does
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    assert client.get("/api/auth/me/").status_code == 401
    client.credentials(HTTP_AUTHORIZATION=f"Token {new_token}")
    assert client.get("/api/auth/me/").status_code == 200
