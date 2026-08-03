from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.products.models import Product, ProductHistory
from apps.users.models import User


def resolve_manager(username: str) -> User:
    """Map an X-Manager-Id username to a User row, creating a placeholder if
    needed. A real auth flow will replace this lookup later."""
    name = (username or "manager").strip() or "manager"
    user, _ = User.objects.get_or_create(
        username=name,
        defaults={"email": f"{name}@aims.local"},
    )
    return user


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


class ProductHistoryService:
    """
    Single audit-writing boundary for product changes.
    Product CUD services call this class instead of creating history rows directly, 
     keeping history format consistent across create/update/delete
    """

    @staticmethod
    @transaction.atomic
    def log(
        *,
        product: Product,
        action_type: str,
        performed_by: str,
        changes: dict | None = None,
        reason: str = "",
    ) -> ProductHistory:
        return ProductHistory.objects.create(
            product=product,
            action_type=action_type,
            performed_by=resolve_manager(performed_by),
            changes=_json_safe(changes or {}),
            reason=reason,
        )
