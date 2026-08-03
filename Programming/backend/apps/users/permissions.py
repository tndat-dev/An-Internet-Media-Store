"""Role-based DRF permissions for internal users.

Applied per-view (e.g. manager order endpoints). There is intentionally no global
DEFAULT_PERMISSION_CLASSES so the public/customer endpoints stay open.
"""

from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    required_role: str | None = None
    # ADMIN is treated as a superset that satisfies any role check.
    ADMIN_ROLE = "ADMIN"

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        if not hasattr(user, "has_role"):  # a django.contrib.auth user, not ours
            return False
        if user.has_role(self.ADMIN_ROLE):
            return True
        return bool(self.required_role) and user.has_role(self.required_role)


class IsProductManager(HasRole):
    required_role = "PRODUCT_MANAGER"


class IsAdministrator(HasRole):
    required_role = "ADMIN"
