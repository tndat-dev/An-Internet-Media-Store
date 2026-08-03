"""Resolve the acting internal user for a request.

Bridges the interim ``X-Manager-Id`` header mechanism and real token auth: once
Phase B token auth populates ``request.user`` with an ``apps.users.User``, that
authenticated user wins; otherwise we fall back to the header (kept for backward
compatibility while the frontend migrates). The header path can be removed once
all manager/admin clients send a token.
"""

from apps.products.history_service import resolve_manager
from apps.users.models import User


def resolve_actor(request) -> User:
    user = getattr(request, "user", None)
    if isinstance(user, User) and getattr(user, "is_authenticated", False):
        return user
    return resolve_manager(request.headers.get("X-Manager-Id", "manager"))
