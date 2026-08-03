import pytest
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient

from apps.users.models import (
    AuthToken,
    Role,
    User,
    UserAuditAction,
    UserAuditLog,
    UserRole,
    UserStatusChoice,
)

pytestmark = pytest.mark.django_db
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


def make_user(username, role_name=None, password="pass12345", status=UserStatusChoice.ACTIVE):
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


def client_for(user):
    token = AuthToken.create_for(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def admin_client():
    admin = make_user("admin", "ADMIN")
    # ensure PRODUCT_MANAGER role exists for assignment tests
    Role.objects.get_or_create(role_name="PRODUCT_MANAGER")
    return admin, client_for(admin)


def test_non_admin_cannot_access_admin_endpoints():
    pm = make_user("pm", "PRODUCT_MANAGER")
    assert APIClient().get("/api/admin/users/").status_code == 401  # anon
    assert client_for(pm).get("/api/admin/users/").status_code == 403  # PM lacks ADMIN


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_admin_creates_user_hashed_no_password_in_response_and_emails(django_capture_on_commit_callbacks):
    _, client = admin_client()
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            "/api/admin/users/",
            {"username": "newpm", "email": "newpm@aims.local", "fullName": "New PM", "roleNames": ["PRODUCT_MANAGER"]},
            format="json",
        )

    assert response.status_code == 201
    assert "password" not in response.data and "password_hash" not in response.data
    assert response.data["roles"] == ["PRODUCT_MANAGER"]
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["newpm@aims.local"]
    user = User.objects.get(username="newpm")
    assert UserAuditLog.objects.filter(action=UserAuditAction.USER_CREATED, target_user=user).exists()


def test_create_user_rejects_unknown_role_and_duplicates():
    _, client = admin_client()
    bad_role = client.post(
        "/api/admin/users/",
        {"username": "x", "email": "x@aims.local", "roleNames": ["NOPE"]},
        format="json",
    )
    assert bad_role.status_code == 400

    client.post("/api/admin/users/", {"username": "dupe", "email": "dupe@aims.local"}, format="json")
    dup = client.post("/api/admin/users/", {"username": "dupe", "email": "other@aims.local"}, format="json")
    assert dup.status_code == 400


def test_admin_cannot_block_self():
    admin, client = admin_client()
    response = client.post(f"/api/admin/users/{admin.user_id}/status/", {"status": "BLOCKED"}, format="json")
    assert response.status_code == 400
    admin.refresh_from_db()
    assert admin.status == UserStatusChoice.ACTIVE


def test_admin_cannot_remove_own_admin_role():
    admin, client = admin_client()
    response = client.post(f"/api/admin/users/{admin.user_id}/roles/", {"roleNames": ["PRODUCT_MANAGER"]}, format="json")
    assert response.status_code == 400


def test_block_user_revokes_their_token():
    _, client = admin_client()
    victim = make_user("victim", "PRODUCT_MANAGER")
    victim_token = AuthToken.create_for(victim).key
    victim_client = APIClient()
    victim_client.credentials(HTTP_AUTHORIZATION=f"Token {victim_token}")
    assert victim_client.get("/api/auth/me/").status_code == 200

    resp = client.post(f"/api/admin/users/{victim.user_id}/status/", {"status": "BLOCKED"}, format="json")
    assert resp.status_code == 200
    assert victim_client.get("/api/auth/me/").status_code == 401  # token revoked


def test_set_roles_replaces_and_validates():
    _, client = admin_client()
    target = make_user("rtarget", "PRODUCT_MANAGER")
    ok = client.post(f"/api/admin/users/{target.user_id}/roles/", {"roleNames": []}, format="json")
    assert ok.status_code == 200 and ok.data["roles"] == []
    unknown = client.post(f"/api/admin/users/{target.user_id}/roles/", {"roleNames": ["GHOST"]}, format="json")
    assert unknown.status_code == 400


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_reset_password_revokes_token_emails_and_audits(django_capture_on_commit_callbacks):
    _, client = admin_client()
    target = make_user("rp", "PRODUCT_MANAGER")
    target_token = AuthToken.create_for(target).key
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(f"/api/admin/users/{target.user_id}/reset-password/", {}, format="json")

    assert resp.status_code == 204
    assert not AuthToken.objects.filter(user=target).exists()  # revoked
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["rp@aims.local"]
    assert UserAuditLog.objects.filter(action=UserAuditAction.PASSWORD_RESET, target_user=target).exists()


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_change_notifies_both_addresses(django_capture_on_commit_callbacks):
    _, client = admin_client()
    target = make_user("ec", "PRODUCT_MANAGER")
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.patch(f"/api/admin/users/{target.user_id}/", {"email": "ec-new@aims.local"}, format="json")

    assert resp.status_code == 200
    recipients = {addr for m in mail.outbox for addr in m.to}
    assert {"ec@aims.local", "ec-new@aims.local"} <= recipients
    assert UserAuditLog.objects.filter(action=UserAuditAction.USER_EMAIL_CHANGED, target_user=target).exists()


def test_audit_log_list_is_admin_only():
    _, client = admin_client()
    make_user("pm2", "PRODUCT_MANAGER")
    assert client.get("/api/admin/audit-logs/").status_code == 200
    pm = User.objects.get(username="pm2")
    assert client_for(pm).get("/api/admin/audit-logs/").status_code == 403
