from django.urls import path

from apps.carts.views import CartDetailView, CartItemCreateView, CartItemDetailView


urlpatterns = [
    path("", CartDetailView.as_view(), name="cart-detail"),
    path("items/", CartItemCreateView.as_view(), name="cart-item-create"),
    path("items/<uuid:item_id>/", CartItemDetailView.as_view(), name="cart-item-detail"),
]
