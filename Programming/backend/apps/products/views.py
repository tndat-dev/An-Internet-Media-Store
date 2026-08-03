from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.models import ProductHistory
from apps.products.selectors import ProductSelector
from apps.products.serializers import (
    CustomerProductSerializer,
    ProductDeleteSerializer,
    ProductHistorySerializer,
    ProductPatchSerializer,
    ProductSerializer,
    ProductWriteSerializer,
)
from apps.products.services import ProductService
from apps.users.identity import resolve_actor
from apps.users.permissions import IsProductManager


def _manager_id(request) -> str:
    # Prefer the authenticated product manager (token); falls back to the legacy
    # X-Manager-Id header for any still-open path. Writes now require auth (below).
    return resolve_actor(request).username


def _raise_drf_validation(error: DjangoValidationError) -> None:
    raise ValidationError(error.message_dict if hasattr(error, "message_dict") else error.messages)


def _is_customer_scope(request) -> bool:
    return request.query_params.get("scope") == "customer"


class CustomerProductPagination(PageNumberPagination):
    """Paginates customer search/filter results — "display all related products on
    each search page" (Problem Statement). 20 per page, client may override up to 100."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CustomerProductListView(APIView):
    """Customer catalogue read: public, paginated, customer-facing DTO.

    Single responsibility: serve the customer product list. Changes to customer
    browsing (pagination, filters, sort) live here and nowhere else.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        products = ProductSelector.list_for_customer(
            search=request.query_params.get("search", ""),
            category=request.query_params.get("category", ""),
            min_price=request.query_params.get("min_price", ""),
            max_price=request.query_params.get("max_price", ""),
            sort=request.query_params.get("sort", ""),
        )
        paginator = CustomerProductPagination()
        page = paginator.paginate_queryset(products, request)
        return paginator.get_paginated_response(CustomerProductSerializer(page, many=True).data)


class ManagerProductListCreateView(APIView):
    """Manager catalogue: list (optionally including deleted) + create a product.

    Single responsibility: the manager product command/list surface. Listing is
    open (the manager workspace is gated in the UI); creating requires a manager.
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsProductManager()]
        return [AllowAny()]

    def get(self, request):
        products = ProductSelector.list_for_manager(
            include_deleted=request.query_params.get("include_deleted") == "true",
            search=request.query_params.get("search", ""),
        )
        return Response(ProductSerializer(products, many=True).data)

    def post(self, request):
        serializer = ProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            product = ProductService.create_product(
                data=dict(serializer.validated_data),
                manager_id=_manager_id(request),
            )
        except DjangoValidationError as error:
            _raise_drf_validation(error)
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


# Design note (refactored): the customer catalogue read and the manager
# command/list surface used to share one class (SRP smell). They now live in the
# two single-responsibility views above. This thin dispatcher preserves the single
# /api/products/ endpoint and its permission ladder (public GET, manager-only POST)
# so the HTTP contract and the frontend are unchanged. See the Design Patterns report.
class ProductListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsProductManager()]
        return [AllowAny()]

    def get(self, request):
        if _is_customer_scope(request):
            return CustomerProductListView().get(request)
        return ManagerProductListCreateView().get(request)

    def post(self, request):
        return ManagerProductListCreateView().post(request)


class ProductDetailView(APIView):
    """
    Coupling/Cohesion level:
    - Coupling: Data coupling with ProductSelector by product_id; stamp coupling with serializers and ProductService.
    - Cohesion: Procedural cohesion.

    Reason why: The class translates detail HTTP actions while delegating read behavior and manager mutations to dedicated modules.
    """

    def get_permissions(self):
        # Read stays public; update requires a manager.
        if self.request.method == "PATCH":
            return [IsProductManager()]
        return [AllowAny()]

    def get_object(self, product_id, *, customer_scope: bool = False):
        try:
            if customer_scope:
                return ProductSelector.get_for_customer(product_id)
            return ProductSelector.get_for_manager(product_id)
        except Exception as exc:
            raise NotFound("Product not found.") from exc

    def get(self, request, product_id):
        product = self.get_object(product_id, customer_scope=_is_customer_scope(request))
        if _is_customer_scope(request):
            return Response(CustomerProductSerializer(product).data)
        return Response(ProductSerializer(product).data)

    def patch(self, request, product_id):
        product = self.get_object(product_id)
        serializer = ProductPatchSerializer(instance=product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            updated_product = ProductService.update_product(
                product=product,
                data=dict(serializer.validated_data),
                manager_id=_manager_id(request),
            )
        except DjangoValidationError as error:
            _raise_drf_validation(error)
        return Response(ProductSerializer(updated_product).data)


class ProductDeleteView(APIView):
    """
    Coupling/Cohesion level:
    - Coupling: Data coupling with ProductDeleteSerializer and ProductService through product_ids.
    - Cohesion: Functional cohesion.

    Reason why: The class has one endpoint responsibility: validate and execute product delete/deactivate requests.
    """

    permission_classes = [IsProductManager]

    def post(self, request):
        serializer = ProductDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            products = ProductService.delete_products(
                product_ids=[str(product_id) for product_id in serializer.validated_data["product_ids"]],
                manager_id=_manager_id(request),
            )
        except DjangoValidationError as error:
            _raise_drf_validation(error)
        return Response(ProductSerializer(products, many=True).data)


class ProductHistoryListView(APIView):
    """
    Coupling/Cohesion level:
    - Coupling: Stamp coupling with ProductHistory queryset and ProductHistorySerializer.
    - Cohesion: Functional cohesion.

    Reason why: The class only exposes product history records for manager review.
    """

    permission_classes = [IsProductManager]

    def get(self, request):
        histories = ProductHistory.objects.select_related("product")
        product_id = request.query_params.get("product_id")
        if product_id:
            histories = histories.filter(product_id=product_id)
        return Response(ProductHistorySerializer(histories[:100], many=True).data)
