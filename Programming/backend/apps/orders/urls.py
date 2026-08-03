from django.urls import path

from apps.orders.views import (
    ManagerApproveOrderView,
    ManagerMarkRefundedView,
    ManagerOrderDetailView,
    ManagerPendingOrderListView,
    ManagerRefundListView,
    ManagerRejectOrderView,
    OrderCancelView,
    OrderConfirmView,
    OrderDeliveryPreviewView,
    OrderDeliveryView,
    OrderDraftView,
    OrderInvoiceView,
    OrderMarkPaidView,
    PublicOrderLookupView,
)


urlpatterns = [
    path("draft/", OrderDraftView.as_view(), name="order-draft"),
    # Manager review queue — must precede the bare "<uuid:token>/" catch-all.
    path("manage/pending/", ManagerPendingOrderListView.as_view(), name="order-manage-pending"),
    path("manage/refunds/", ManagerRefundListView.as_view(), name="order-manage-refunds"),
    path("manage/<uuid:order_id>/", ManagerOrderDetailView.as_view(), name="order-manage-detail"),
    path("manage/<uuid:order_id>/approve/", ManagerApproveOrderView.as_view(), name="order-manage-approve"),
    path("manage/<uuid:order_id>/reject/", ManagerRejectOrderView.as_view(), name="order-manage-reject"),
    path("manage/<uuid:order_id>/mark-refunded/", ManagerMarkRefundedView.as_view(), name="order-manage-mark-refunded"),
    path("<uuid:order_id>/delivery/", OrderDeliveryView.as_view(), name="order-delivery"),
    path("<uuid:order_id>/delivery/preview/", OrderDeliveryPreviewView.as_view(), name="order-delivery-preview"),
    path("<uuid:order_id>/invoice/", OrderInvoiceView.as_view(), name="order-invoice"),
    path("<uuid:order_id>/mark-paid/", OrderMarkPaidView.as_view(), name="order-mark-paid"),
    path("<uuid:cancel_token>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
    path("", OrderConfirmView.as_view(), name="order-confirm"),
    path("<uuid:token>/", PublicOrderLookupView.as_view(), name="public-order-lookup"),
]
