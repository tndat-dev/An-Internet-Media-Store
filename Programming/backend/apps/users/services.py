"""Authentication, registration, and admin user/role management workflows.

Passwords are always stored hashed (django make_password) and verified with
check_password. The admin never sees a real password: admin-created accounts get
a server-generated initial password that is emailed to the user, never returned
in API responses and never written to logs/audit detail.

All sensitive mutations record a UserAuditLog entry and (where relevant) notify
the affected user by email. Self-lockout and last-active-admin guards live here in
the service layer, inside transaction.atomic, so they apply to every entry point.
"""

import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.users import notifications
from apps.users.models import (
    AuthToken,
    Role,
    User,
    UserAuditAction,
    UserAuditLog,
    UserRole,
    UserStatusChoice,
)

MIN_PASSWORD_LENGTH = 8
ADMIN_ROLE = "ADMIN"
CUSTOMER_ROLE = "CUSTOMER"


def _generate_password() -> str:
    """Server-generated initial/reset password (>=12 chars, url-safe)."""
    return secrets.token_urlsafe(12)


def revoke_tokens(user: User) -> None:
    """Delete all auth tokens for a user (immediate session revocation)."""
    AuthToken.objects.filter(user=user).delete()


def _validate_password_strength(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            {"password": f"Password must be at least {MIN_PASSWORD_LENGTH} characters."}
        )


def _role_names(user: User) -> list[str]:
    return [ur.role.role_name for ur in user.user_roles.select_related("role").all()]


def _other_active_admin_exists(exclude_user: User) -> bool:
    return (
        User.objects.filter(status=UserStatusChoice.ACTIVE, user_roles__role__role_name=ADMIN_ROLE)
        .exclude(pk=exclude_user.pk)
        .exists()
    )


class AuditService:
    @staticmethod
    def record(actor, target, action: str, detail: dict | None = None) -> None:
        UserAuditLog.objects.create(
            actor=actor if isinstance(actor, User) else None,
            target_user=target,
            action=action,
            detail=detail or {},
        )


class AuthService:
    @staticmethod
    def login(username: str, password: str) -> tuple[User, AuthToken]:
        identifier = (username or "").strip()
        if not identifier or not password:
            raise ValidationError({"detail": "Username and password are required."})

        # Accept either a username or an email address (mockup login uses email).
        user = User.objects.filter(username=identifier).first() or User.objects.filter(email__iexact=identifier).first()
        if user is None:
            # Same message for unknown user and bad password (no account enumeration).
            raise ValidationError({"detail": "Invalid username or password."})

        if not user.password_hash or not check_password(password, user.password_hash):
            raise ValidationError({"detail": "Invalid username or password."})

        if user.status != UserStatusChoice.ACTIVE:
            raise ValidationError({"detail": "User account is not active."})

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        token = AuthToken.create_for(user)
        return user, token

    @staticmethod
    def logout(user: User) -> None:
        AuthToken.objects.filter(user=user).delete()

    @staticmethod
    @transaction.atomic
    def register(*, username: str, email: str, password: str, full_name: str = "", phone: str = "") -> tuple[User, AuthToken]:
        """Public self-registration. Always creates a CUSTOMER account — the role
        is forced server-side so this endpoint can never mint a PM/Admin."""
        username = (username or "").strip()
        email = (email or "").strip()
        if not username or not email:
            raise ValidationError({"detail": "Username and email are required."})
        _validate_password_strength(password)
        if User.objects.filter(username=username).exists():
            raise ValidationError({"username": "Username already exists."})
        if User.objects.filter(email=email).exists():
            raise ValidationError({"email": "Email already exists."})

        user = User.objects.create(
            username=username,
            email=email,
            full_name=full_name.strip(),
            phone=phone.strip(),
            password_hash=make_password(password),
            status=UserStatusChoice.ACTIVE,
        )
        role, _ = Role.objects.get_or_create(
            role_name=CUSTOMER_ROLE,
            defaults={"description": "Customer — self-registered shopper account."},
        )
        UserRole.objects.create(user=user, role=role)
        token = AuthToken.create_for(user)
        return user, token

    @staticmethod
    @transaction.atomic
    def change_password(user: User, old_password: str, new_password: str) -> AuthToken:
        """Optional self-service password change. Rotates the token (caller must
        replace it with the returned key)."""
        if not user.password_hash or not check_password(old_password, user.password_hash):
            raise ValidationError({"oldPassword": "Incorrect password."})
        if new_password == old_password:
            raise ValidationError({"newPassword": "New password must differ from the old password."})
        _validate_password_strength(new_password)

        user.password_hash = make_password(new_password)
        user.save(update_fields=["password_hash"])
        AuditService.record(user, user, UserAuditAction.PASSWORD_CHANGED, {})
        return AuthToken.create_for(user)  # rotate


class RoleService:
    @staticmethod
    def list_roles():
        return Role.objects.all()

    @staticmethod
    @transaction.atomic
    def create_role(actor: User, *, role_name: str, description: str = "") -> Role:
        role_name = (role_name or "").strip()
        if not role_name:
            raise ValidationError({"roleName": "Role name is required."})
        if Role.objects.filter(role_name=role_name).exists():
            raise ValidationError({"roleName": "Role already exists."})
        role = Role.objects.create(role_name=role_name, description=description.strip())
        AuditService.record(actor, None, UserAuditAction.ROLE_CREATED, {"roleName": role_name})
        return role


class AdminUserService:
    """Administrator-only user management. Every method takes the acting admin
    explicitly and enforces guards before mutating."""

    @staticmethod
    def _resolve_roles(role_names: list[str]) -> list[Role]:
        names = [n.strip() for n in (role_names or []) if n and n.strip()]
        roles = list(Role.objects.filter(role_name__in=names))
        if len(roles) != len(set(names)):
            found = {r.role_name for r in roles}
            unknown = sorted(set(names) - found)
            raise ValidationError({"roleNames": f"Unknown role(s): {', '.join(unknown)}"})
        return roles

    @staticmethod
    def _apply_roles(user: User, roles: list[Role]) -> None:
        desired = {r.role_id for r in roles}
        UserRole.objects.filter(user=user).exclude(role_id__in=desired).delete()
        for role in roles:
            UserRole.objects.get_or_create(user=user, role=role)

    @staticmethod
    def list_users():
        return User.objects.prefetch_related("user_roles__role").all()

    @staticmethod
    def get_user(user_id: str) -> User:
        return User.objects.prefetch_related("user_roles__role").get(user_id=user_id)

    @staticmethod
    @transaction.atomic
    def create_user(actor: User, *, username: str, email: str, full_name: str = "", phone: str = "", role_names=None) -> User:
        username = (username or "").strip()
        email = (email or "").strip()
        if not username or not email:
            raise ValidationError({"detail": "Username and email are required."})
        if User.objects.filter(username=username).exists():
            raise ValidationError({"username": "Username already exists."})
        if User.objects.filter(email=email).exists():
            raise ValidationError({"email": "Email already exists."})
        roles = AdminUserService._resolve_roles(role_names or [])

        initial_password = _generate_password()
        user = User.objects.create(
            username=username,
            email=email,
            full_name=full_name.strip(),
            phone=phone.strip(),
            password_hash=make_password(initial_password),
            status=UserStatusChoice.ACTIVE,
        )
        AdminUserService._apply_roles(user, roles)
        AuditService.record(
            actor, user, UserAuditAction.USER_CREATED,
            {"username": username, "email": email, "roles": [r.role_name for r in roles]},
        )
        transaction.on_commit(lambda: notifications.send_account_created(user, initial_password))
        return user

    @staticmethod
    @transaction.atomic
    def set_status(actor: User, target: User, new_status: str) -> User:
        if new_status not in UserStatusChoice.values:
            raise ValidationError({"status": "Invalid status."})
        target = User.objects.select_for_update().get(pk=target.pk)

        deactivating = new_status != UserStatusChoice.ACTIVE
        if deactivating and target.pk == actor.pk:
            raise ValidationError({"status": "You cannot deactivate or block your own account."})
        if (
            deactivating
            and target.status == UserStatusChoice.ACTIVE
            and target.has_role(ADMIN_ROLE)
            and not _other_active_admin_exists(target)
        ):
            raise ValidationError({"status": "At least one active administrator must remain."})

        old_status = target.status
        if old_status == new_status:
            return target
        target.status = new_status
        target.save(update_fields=["status"])
        if deactivating:
            revoke_tokens(target)
        AuditService.record(
            actor, target, UserAuditAction.USER_STATUS_CHANGED, {"from": old_status, "to": new_status}
        )
        if new_status == UserStatusChoice.BLOCKED:
            transaction.on_commit(lambda: notifications.send_account_blocked(target))
        return target

    @staticmethod
    @transaction.atomic
    def set_roles(actor: User, target: User, role_names: list[str]) -> User:
        target = User.objects.select_for_update().get(pk=target.pk)
        roles = AdminUserService._resolve_roles(role_names)
        before = sorted(_role_names(target))
        will_have_admin = any(r.role_name == ADMIN_ROLE for r in roles)

        if target.pk == actor.pk and not will_have_admin and ADMIN_ROLE in before:
            raise ValidationError({"roleNames": "You cannot remove your own administrator role."})
        if (
            ADMIN_ROLE in before
            and not will_have_admin
            and target.status == UserStatusChoice.ACTIVE
            and not _other_active_admin_exists(target)
        ):
            raise ValidationError({"roleNames": "At least one active administrator must remain."})

        AdminUserService._apply_roles(target, roles)
        after = sorted(r.role_name for r in roles)
        AuditService.record(
            actor, target, UserAuditAction.USER_ROLES_CHANGED, {"from": before, "to": after}
        )
        return AdminUserService.get_user(str(target.pk))

    @staticmethod
    @transaction.atomic
    def update_profile(actor: User, target: User, *, full_name=None, phone=None, email=None) -> User:
        target = User.objects.select_for_update().get(pk=target.pk)
        changed = []
        old_email = target.email
        if full_name is not None:
            target.full_name = full_name.strip()
            changed.append("full_name")
        if phone is not None:
            target.phone = phone.strip()
            changed.append("phone")
        email_changed = False
        if email is not None and email.strip() and email.strip() != target.email:
            new_email = email.strip()
            if User.objects.filter(email=new_email).exclude(pk=target.pk).exists():
                raise ValidationError({"email": "Email already exists."})
            target.email = new_email
            changed.append("email")
            email_changed = True

        if not changed:
            return target
        target.save(update_fields=changed)

        if email_changed:
            AuditService.record(
                actor, target, UserAuditAction.USER_EMAIL_CHANGED, {"from": old_email, "to": target.email}
            )
            new_email = target.email
            transaction.on_commit(lambda: notifications.send_email_changed(target, old_email, new_email))
        else:
            AuditService.record(actor, target, UserAuditAction.USER_PROFILE_UPDATED, {"fields": changed})
        return AdminUserService.get_user(str(target.pk))

    @staticmethod
    @transaction.atomic
    def reset_password(actor: User, target: User) -> None:
        target = User.objects.select_for_update().get(pk=target.pk)
        new_password = _generate_password()
        target.password_hash = make_password(new_password)
        target.save(update_fields=["password_hash"])
        revoke_tokens(target)
        AuditService.record(actor, target, UserAuditAction.PASSWORD_RESET, {})
        transaction.on_commit(lambda: notifications.send_password_reset(target, new_password))
