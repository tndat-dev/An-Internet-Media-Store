from django.contrib import admin
from django.conf import settings
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    return JsonResponse(
        {
            "status": "ok",
            "supabaseConfigured": bool(
                settings.SUPABASE_URL and settings.SUPABASE_PUBLISHABLE_KEY
            ),
        }
    )


urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/health/", health_check, name="health-check"),
    path("api/auth/", include("apps.users.urls")),
    path("api/admin/", include("apps.users.admin_urls")),
    path("api/cart/", include("apps.carts.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/products/", include("apps.products.urls")),
    path("api/payments/", include("apps.payments.urls")),
]
