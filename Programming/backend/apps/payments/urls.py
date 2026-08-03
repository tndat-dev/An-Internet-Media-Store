from django.urls import path

from .views import (
    PayPalCaptureView,
    PayPalPaymentView,
    PayPalRefundView,
    VietQRQRCodeView,
    VietQRStatusView,
    VietQRCallbackTokenView,
    VietQRTransactionSyncView,
    VietQRTestCallbackView,
)

urlpatterns = [
    path("paypal/initiate/", PayPalPaymentView.as_view(), name="paypal-initiate"),
    path("paypal/capture/", PayPalCaptureView.as_view(), name="paypal-capture"),
    path("paypal/refund/", PayPalRefundView.as_view(), name="paypal-refund"),

    path("vietqr/qr-code/", VietQRQRCodeView.as_view(), name="vietqr-qr-code"),
    path("vietqr/test-callback/", VietQRTestCallbackView.as_view(), name="vietqr-test-callback"),
    path("<int:transaction_id>/status/", VietQRStatusView.as_view(), name="payment-status"),

    # VietQR endpoints under /api/payments/
    path("vietqr/token-generate/", VietQRCallbackTokenView.as_view(), name="vietqr-token-generate"),

    # Legacy/provider-compat aliases under /api/payments/.
    # Accept both slash and no-slash forms because external VietQR POST callbacks
    # may target the legacy nested paths exactly, and APPEND_SLASH cannot preserve
    # POST bodies during redirect.
    path("vietqr/api/token_generate", VietQRCallbackTokenView.as_view(), name="vietqr-token-generate-legacy-noslash"),
    path("vietqr/api/token_generate/", VietQRCallbackTokenView.as_view(), name="vietqr-token-generate-legacy"),
    path(
        "vietqr/bank/api/transaction-sync",
        VietQRTransactionSyncView.as_view(),
        name="vietqr-transaction-sync-legacy-noslash",
    ),
    path(
        "vietqr/bank/api/transaction-sync/",
        VietQRTransactionSyncView.as_view(),
        name="vietqr-transaction-sync-legacy",
    ),
]
