"""Internal users, roles, role assignments, auth tokens, and audit log.

Provides referential integrity for `ProductHistory.performed_by` and
`Order.processed_by`, plus token-based authentication (`AuthToken`) for the
custom `User` model (NOT django.contrib.auth) and an audit trail of sensitive
user/role management actions.
"""

import secrets
import uuid

from django.db import models


class UserStatusChoice(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    DEACTIVATED = "DEACTIVATED", "Deactivated"
    BLOCKED = "BLOCKED", "Blocked"


class User(models.Model):
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(max_length=255, unique=True)
    password_hash = models.TextField(blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(
        max_length=20,
        choices=UserStatusChoice.choices,
        default=UserStatusChoice.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username

    # --- DRF auth compatibility (this is app identity, NOT django.contrib.auth) ---
    # Properties (not fields) → no migration. Let DRF treat an authenticated
    # apps.users.User like an auth user (request.user.*).
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def is_active(self) -> bool:
        return self.status == UserStatusChoice.ACTIVE

    def has_role(self, role_name: str) -> bool:
        return self.user_roles.filter(role__role_name=role_name).exists()


class Role(models.Model):
    role_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["role_name"]

    def __str__(self) -> str:
        return self.role_name


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uq_user_roles_user_role"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.role_id}"


class AuthToken(models.Model):
    """Opaque bearer token for an internal user (custom, not DRF's authtoken,
    because apps.users.User is not AUTH_USER_MODEL). One active token per user."""

    key = models.CharField(max_length=64, primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="auth_token")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Token for {self.user_id}"

    @classmethod
    def create_for(cls, user: "User") -> "AuthToken":
        """Issue a fresh token for the user, replacing any existing one (rotation)."""
        cls.objects.filter(user=user).delete()
        return cls.objects.create(key=secrets.token_hex(32), user=user)


class UserAuditAction(models.TextChoices):
    USER_CREATED = "USER_CREATED", "User created"
    USER_STATUS_CHANGED = "USER_STATUS_CHANGED", "User status changed"
    USER_ROLES_CHANGED = "USER_ROLES_CHANGED", "User roles changed"
    USER_PROFILE_UPDATED = "USER_PROFILE_UPDATED", "User profile updated"
    USER_EMAIL_CHANGED = "USER_EMAIL_CHANGED", "User email changed"
    PASSWORD_RESET = "PASSWORD_RESET", "Password reset (admin)"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed (self)"
    ROLE_CREATED = "ROLE_CREATED", "Role created"


class UserAuditLog(models.Model):
    """Audit trail for sensitive user/role management actions.

    Detail is structured JSON and must NEVER contain passwords or hashes — only
    what changed (e.g. {"from": "ACTIVE", "to": "BLOCKED"}).
    """

    audit_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_actions"
    )
    target_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_records"
    )
    action = models.CharField(max_length=32, choices=UserAuditAction.choices)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} target={self.target_user_id} by {self.actor_id}"
