from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    publishable_key: str
    service_role_key: str = ""

    @property
    def rest_url(self) -> str:
        return f"{self.url.rstrip('/')}/rest/v1"

    def headers(self, *, service_role: bool = False) -> dict[str, str]:
        token = self.service_role_key if service_role and self.service_role_key else self.publishable_key
        return {
            "apikey": token,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }


def get_supabase_config(*, required: bool = False) -> SupabaseConfig | None:
    url = settings.SUPABASE_URL.strip()
    publishable_key = settings.SUPABASE_PUBLISHABLE_KEY.strip()
    service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY.strip()

    if not url or not publishable_key:
        if required:
            raise ImproperlyConfigured(
                "Supabase is not configured. Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY "
                "or NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY."
            )
        return None

    return SupabaseConfig(
        url=url,
        publishable_key=publishable_key,
        service_role_key=service_role_key,
    )
