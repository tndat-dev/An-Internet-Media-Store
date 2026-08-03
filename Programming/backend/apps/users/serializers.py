from rest_framework import serializers

from apps.users.models import Role, User, UserAuditLog, UserStatusChoice


def _roles_of(user: User) -> list[str]:
    return [ur.role.role_name for ur in user.user_roles.select_related("role").all()]


class LoginInputSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})


class RegisterInputSerializer(serializers.Serializer):
    """Public self-registration. No role field — the server forces CUSTOMER."""

    username = serializers.CharField(max_length=100)
    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})
    fullName = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class ChangePasswordSerializer(serializers.Serializer):
    oldPassword = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})
    newPassword = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})


class UserSerializer(serializers.ModelSerializer):
    userId = serializers.UUIDField(source="user_id", read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["userId", "username", "email", "status", "roles"]

    def get_roles(self, user: User) -> list[str]:
        return _roles_of(user)


class AdminUserSerializer(serializers.ModelSerializer):
    """Full read view for admin user management (never exposes password_hash)."""

    userId = serializers.UUIDField(source="user_id", read_only=True)
    fullName = serializers.CharField(source="full_name", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    lastLogin = serializers.DateTimeField(source="last_login", read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "userId", "username", "email", "fullName", "phone",
            "status", "roles", "createdAt", "lastLogin",
        ]

    def get_roles(self, user: User) -> list[str]:
        return _roles_of(user)


class AdminUserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=100)
    email = serializers.EmailField(max_length=255)
    fullName = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    roleNames = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class AdminUserUpdateSerializer(serializers.Serializer):
    # Status changes go through the dedicated /status/ route (single guarded path).
    fullName = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=255, required=False)


class SetStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=UserStatusChoice.choices)


class SetRolesSerializer(serializers.Serializer):
    roleNames = serializers.ListField(child=serializers.CharField())


class RoleSerializer(serializers.ModelSerializer):
    roleId = serializers.UUIDField(source="role_id", read_only=True)
    roleName = serializers.CharField(source="role_name")
    description = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = Role
        fields = ["roleId", "roleName", "description"]


class UserAuditLogSerializer(serializers.ModelSerializer):
    auditId = serializers.UUIDField(source="audit_id", read_only=True)
    actor = serializers.CharField(source="actor.username", read_only=True, default=None)
    targetUser = serializers.CharField(source="target_user.username", read_only=True, default=None)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = UserAuditLog
        fields = ["auditId", "actor", "targetUser", "action", "detail", "createdAt"]
