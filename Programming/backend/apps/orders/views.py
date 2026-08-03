from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView


class PendingOrderPagination(PageNumberPagination):
    """Problem Statement: managers see 30 pending orders per page."""

    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100

from apps.orders.models import Order
from apps.orders.serializers import (
    DeliveryInfoInputSerializer,
    DeliveryPreviewInputSerializer,
    InvoiceSerializer,
    ManagerOrderSerializer,
    OrderConfirmSerializer,
    OrderSerializer,
)
from apps.orders.services import (
    DetailedValidationError,
    OrderCancellationService,
    OrderPlacementService,
    OrderReviewService,
)
from apps.users.identity import resolve_actor
from apps.users.permissions import IsProductManager


def _cart_token(request) -> str:
    token = request.headers.get("X-Cart-Token", "").strip()
    if not token:
        raise ValidationError({"cartToken": "X-Cart-Token header is required."})
    return token


def _raise_validation(error: DjangoValidationError) -> None:
    if hasattr(error, "message_dict"):
        payload = {
            field: messages[0] if isinstance(messages, list) and len(messages) == 1 else messages
            for field, messages in error.message_dict.items()
        }
        raise ValidationError(payload)
    raise ValidationError(error.messages)


# /*
#  * SOLID Review
#  * Principle: SRP
#  * Reason: The order checkout view classes repeat request parsing, exception translation, and service delegation patterns across draft, delivery, invoice, and confirm endpoints.
#  * Impact: Controller behavior is still thin, but duplicated translation logic increases maintenance cost when API error handling changes.
#  * Improvement: Extract shared order API error mapping/base view helpers while keeping each endpoint focused on one HTTP action.
#  */
class OrderDraftView(APIView):
    def post(self, request):
        try:
            order = OrderPlacementService.create_draft_order(_cart_token(request))
        except DetailedValidationError as error:
            return Response(error.payload, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDeliveryView(APIView):
    def post(self, request, order_id):
        serializer = DeliveryInfoInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order = OrderPlacementService.apply_delivery_info(
                order_id=str(order_id),
                delivery_info=serializer.validated_data,
            )
        except ObjectDoesNotExist as error:
            raise NotFound("Order not found.") from error
        except DetailedValidationError as error:
            return Response(error.payload, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(OrderSerializer(order).data)


class OrderDeliveryPreviewView(APIView):
    """POST /api/orders/{id}/delivery/preview/ — live delivery fee + totals for the
    delivery screen Order Summary, without persisting delivery info."""

    def post(self, request, order_id):
        serializer = DeliveryPreviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            totals = OrderPlacementService.preview_delivery(
                order_id=str(order_id),
                province=serializer.validated_data["province"],
                delivery_method=serializer.validated_data.get("deliveryMethod", "STANDARD"),
            )
        except ObjectDoesNotExist as error:
            raise NotFound("Order not found.") from error
        except (DjangoValidationError, ValueError) as error:
            _raise_validation(error if isinstance(error, DjangoValidationError) else DjangoValidationError({"province": str(error)}))
        return Response(
            {
                "subtotalExclVat": f"{totals['total_product_price_excl_vat']:.2f}",
                "vatAmount": f"{totals['vat_amount']:.2f}",
                "totalInclVat": f"{totals['total_product_price_incl_vat']:.2f}",
                "deliveryFee": f"{totals['delivery_fee']:.2f}",
                "totalAmountToPay": f"{totals['total_amount_to_pay']:.2f}",
            }
        )


class OrderInvoiceView(APIView):
    def get(self, request, order_id):
        try:
            invoice = OrderPlacementService.get_invoice(str(order_id))
        except ObjectDoesNotExist as error:
            raise NotFound("Invoice not found.") from error
        return Response(InvoiceSerializer(invoice).data)


class OrderConfirmView(APIView):
    def post(self, request):
        serializer = OrderConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order = OrderPlacementService.confirm_order(str(serializer.validated_data["orderId"]))
        except ObjectDoesNotExist as error:
            raise NotFound("Order not found.") from error
        except DetailedValidationError as error:
            return Response(error.payload, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(OrderSerializer(order).data)


class OrderMarkPaidView(APIView):
    def post(self, request, order_id):
        try:
            order = OrderPlacementService.mark_order_paid(str(order_id))
        except ObjectDoesNotExist as error:
            raise NotFound("Order not found.") from error
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(OrderSerializer(order).data)


class PublicOrderLookupView(APIView):
    def get(self, request, token):
        try:
            order = Order.objects.prefetch_related("items").get(order_view_token=token)
        except ObjectDoesNotExist as error:
            raise NotFound("Order not found.") from error
        return Response(OrderSerializer(order).data)


# /*
#  * SOLID Review
#  * Principle: SRP/DIP
#  * Reason: OrderCancelView directly looks up Order by token before delegating cancellation, mixing public-token retrieval with cancellation workflow coordination.
#  * Impact: Token lookup and cancellation policy become harder to test independently and can duplicate access rules in future public order endpoints.
#  * Improvement: Move token-based order retrieval into a selector/service and keep the view limited to HTTP input/output.
#  */
class OrderCancelView(APIView):
    """POST /api/orders/<cancel_token>/cancel/ — customer cancel before approval.

    Public route keyed by the per-order cancel_token (the token in the customer's
    cancellation link), so it needs no auth.
    """

    def post(self, request, cancel_token):
        try:
            order = Order.objects.get(cancel_token=cancel_token)
        except (ObjectDoesNotExist, ValueError) as error:
            raise NotFound("Order not found.") from error
        try:
            order = OrderCancellationService.cancel_order(order)
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(OrderSerializer(order).data)


class ManagerPendingOrderListView(APIView):
    """GET /api/orders/manage/pending/ — pending-processing review queue."""

    permission_classes = [IsProductManager]

    def get(self, request):
        orders = OrderReviewService.list_pending()
        paginator = PendingOrderPagination()
        page = paginator.paginate_queryset(orders, request)
        return paginator.get_paginated_response(ManagerOrderSerializer(page, many=True).data)


class ManagerOrderDetailView(APIView):
    """GET /api/orders/manage/<id>/ — manager order detail."""

    permission_classes = [IsProductManager]

    def get(self, request, order_id):
        try:
            order = OrderReviewService.get_order_detail(str(order_id))
        except ObjectDoesNotExist as error:
            raise NotFound("Order not found.") from error
        return Response(ManagerOrderSerializer(order).data)


class ManagerApproveOrderView(APIView):
    """POST /api/orders/manage/<id>/approve/ — approve a pending order."""

    permission_classes = [IsProductManager]

    def post(self, request, order_id):
        try:
            order = OrderReviewService.approve_order(str(order_id), resolve_actor(request))
        except ObjectDoesNotExist as error:
            raise NotFound("Order not found.") from error
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(ManagerOrderSerializer(order).data)


class ManagerRejectOrderView(APIView):
    """POST /api/orders/manage/<id>/reject/ — reject a pending order (restores
    stock and issues a refund)."""

    permission_classes = [IsProductManager]

    def post(self, request, order_id):
        reason = str(request.data.get("reason", "")).strip()
        try:
            order = OrderReviewService.reject_order(str(order_id), resolve_actor(request), reason)
        except ObjectDoesNotExist as error:
            raise NotFound("Order not found.") from error
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(ManagerOrderSerializer(order).data)


class ManagerRefundListView(APIView):
    """GET /api/orders/manage/refunds/ — cancelled/rejected VietQR orders that
    need (or have had) a manual refund."""

    permission_classes = [IsProductManager]

    def get(self, request):
        orders = OrderReviewService.list_manual_refunds()
        paginator = PendingOrderPagination()
        page = paginator.paginate_queryset(orders, request)
        return paginator.get_paginated_response(ManagerOrderSerializer(page, many=True).data)


class ManagerMarkRefundedView(APIView):
    """POST /api/orders/manage/<id>/mark-refunded/ — record that the manager has
    manually refunded a VietQR order."""

    permission_classes = [IsProductManager]

    def post(self, request, order_id):
        note = str(request.data.get("note", "")).strip()
        try:
            order = OrderReviewService.mark_refund_complete(str(order_id), resolve_actor(request), note)
        except ObjectDoesNotExist as error:
            raise NotFound("Order not found.") from error
        except DjangoValidationError as error:
            _raise_validation(error)
        return Response(ManagerOrderSerializer(order).data)
