import pytest
from rest_framework.test import APIClient

from apps.users.models import User

pytestmark = pytest.mark.django_db


def test_register_creates_customer_account_and_returns_token():
    client = APIClient()
    response = client.post(
        "/api/auth/register/",
        {"username": "shopper", "email": "shopper@example.com", "password": "secret123", "fullName": "Le Shopper"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["token"]
    assert response.data["user"]["roles"] == ["CUSTOMER"]
    user = User.objects.get(username="shopper")
    assert user.full_name == "Le Shopper"
    assert user.password_hash and "secret123" not in user.password_hash  # hashed


def test_register_cannot_self_assign_privileged_role():
    client = APIClient()
    response = client.post(
        "/api/auth/register/",
        {"username": "sneaky", "email": "sneaky@example.com", "password": "secret123", "roleNames": ["ADMIN"]},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["user"]["roles"] == ["CUSTOMER"]  # server forced CUSTOMER


def test_register_rejects_duplicate_and_weak_password():
    client = APIClient()
    client.post(
        "/api/auth/register/",
        {"username": "dup", "email": "dup@example.com", "password": "secret123"},
        format="json",
    )
    dup = client.post(
        "/api/auth/register/",
        {"username": "dup", "email": "other@example.com", "password": "secret123"},
        format="json",
    )
    weak = client.post(
        "/api/auth/register/",
        {"username": "weaky", "email": "weak@example.com", "password": "short"},
        format="json",
    )

    assert dup.status_code == 400
    assert weak.status_code == 400


def test_registered_customer_can_login():
    client = APIClient()
    client.post(
        "/api/auth/register/",
        {"username": "buyer", "email": "buyer@example.com", "password": "secret123"},
        format="json",
    )
    login = client.post(
        "/api/auth/login/", {"username": "buyer", "password": "secret123"}, format="json"
    )

    assert login.status_code == 200
    assert "CUSTOMER" in login.data["user"]["roles"]
