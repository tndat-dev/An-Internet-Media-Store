from django.urls import path

from apps.products.views import (
    ProductDeleteView,
    ProductDetailView,
    ProductHistoryListView,
    ProductListCreateView,
)


urlpatterns = [
    path("", ProductListCreateView.as_view(), name="product-list-create"),
    path("delete/", ProductDeleteView.as_view(), name="product-delete"),
    path("histories/", ProductHistoryListView.as_view(), name="product-history-list"),
    path("<uuid:product_id>/", ProductDetailView.as_view(), name="product-detail"),
]
