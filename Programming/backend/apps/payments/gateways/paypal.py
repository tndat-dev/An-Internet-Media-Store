"""
Class: PayPalGateway

Coupling Level:
- Data Coupling with PaymentGateway (base) because it implements the abstract
  interface and communicates via well-defined DTOs (PaymentResult, CaptureResult,
  RefundResult) — only necessary data is exchanged.
- Data Coupling with PaymentService because PaymentService passes only primitive
  values (order_id, amount, currency, return_url) — no large objects are passed.
- Stamp Coupling (minor) with requests library response objects — the full
  HTTP response is received but only status_code and json() are used. This is
  acceptable as an external library boundary.

Cohesion Level:
- Functional Cohesion because every method in this class serves a single
  responsibility: interacting with the PayPal REST API.
  create_payment → create a PayPal order
  capture_payment → capture an approved PayPal order
  refund_payment → issue a PayPal refund
  _get_access_token → internal helper to authenticate with PayPal OAuth2

Reason:
All PayPal-specific logic (OAuth token, API base URL, endpoint paths, request
format) is isolated here. PaymentService never imports `requests` or knows
PayPal endpoint details. This makes it easy to swap PayPal for another provider
by replacing only this file.
"""

import logging
from typing import Optional

import requests

from .base import CaptureResult, PaymentGateway, PaymentResult, RefundResult

logger = logging.getLogger(__name__)


# /*
#  * SOLID Review
#  * Principle: SRP
#  * Reason: PayPalGateway combines PayPal order creation, capture, refund, OAuth token caching, mock-mode behavior, and HTTP error mapping in one concrete gateway.
#  * Impact: Provider transport changes, auth changes, and local demo behavior can force edits in the same class and make focused tests more complex.
#  * Improvement: Extract token management and mock behavior into collaborators while keeping this class focused on PayPal API mapping.
#  */
class PayPalGateway(PaymentGateway):
    """
    Concrete PaymentGateway implementation for PayPal REST API v2 (Sandbox/Live).

    Coupling Level:
    - Data Coupling with PaymentGateway (implements the abstract interface and
      communicates via small DTOs). Minimal knowledge of caller's internals is
      required.

    Cohesion Level:
    - Functional Cohesion: all methods are focused on PayPal operations
      (create, capture, refund, auth token management).

    Reason:
    - Encapsulates all PayPal-specific logic (OAuth, endpoints, payload formats)
      so other layers (services, views) do not depend on PayPal SDK or HTTP
      details. This isolates change when switching providers.
    """

    SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
    LIVE_BASE = "https://api-m.paypal.com"

    def __init__(self, client_id: str, client_secret: str, sandbox: bool = True):
        # Blank/missing credentials fall back to mock mode (used by tests and local
        # demos with no PayPal Sandbox keys). Real OAuth runs only when creds exist.
        self._client_id = client_id if str(client_id).strip() else "MOCK"
        self._client_secret = client_secret
        self._base_url = self.SANDBOX_BASE if sandbox else self.LIVE_BASE
        self._access_token: Optional[str] = None

    # ------------------------------------------------------------------
    # Public gateway interface
    # ------------------------------------------------------------------

    def create_payment(
        self,
        order_id: str,
        amount: float,
        currency: str,
        return_url: str,
        cancel_url: str,
        description: str = "",
    ) -> PaymentResult:
        """
        Create a PayPal Order and return the buyer approval URL.
        Maps to: POST /v2/checkout/orders
        """
        # Explicit mock mode only when configured on purpose.
        if str(self._client_id).upper() == "MOCK":
            provider_order_id = f"MOCK-ORDER-{order_id}"
            approval_url = f"https://mock.paypal/approve/{provider_order_id}"
            raw = {"mock": True, "approve_url": approval_url}
            return PaymentResult(success=True, transaction_id=provider_order_id, approval_url=approval_url, raw_response=raw)

        token = self._get_access_token()
        if not token:
            return PaymentResult(success=False, error_message="Failed to obtain PayPal access token")

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": order_id,
                    "description": description or f"AIMS Order {order_id}",
                    "amount": {
                        "currency_code": currency.upper(),
                        "value": f"{amount:.2f}",
                    },
                }
            ],
            "application_context": {
                "return_url": return_url,
                "cancel_url": cancel_url,
                "brand_name": "AIMS Store",
                "landing_page": "LOGIN",
                "user_action": "PAY_NOW",
            },
        }

        try:
            response = requests.post(
                f"{self._base_url}/v2/checkout/orders",
                json=payload,
                headers=self._auth_headers(),
                timeout=10,
            )
            try:
                data = response.json()
            except ValueError:
                data = {"message": response.text or "Invalid response from PayPal"}

            if response.status_code == 201:
                approval_url = next(
                    (link["href"] for link in data.get("links", []) if link["rel"] == "approve"),
                    None,
                )
                if not approval_url:
                    logger.error("PayPal create_payment missing approval link: %s", data)
                    return PaymentResult(
                        success=False,
                        error_message=data.get("message", "Approval URL not returned by PayPal"),
                        raw_response=data,
                    )
                return PaymentResult(
                    success=True,
                    transaction_id=data["id"],
                    approval_url=approval_url,
                    raw_response=data,
                )

            logger.error("PayPal create_payment failed: %s", data)
            return PaymentResult(
                success=False,
                error_message=data.get("message") or data.get("error_description") or "Unknown PayPal error",
                raw_response=data,
            )

        except requests.RequestException as exc:
            logger.exception("PayPal create_payment network error")
            return PaymentResult(success=False, error_message=str(exc))

    def capture_payment(self, provider_order_id: str) -> CaptureResult:
        """
        Capture an approved PayPal order.
        Maps to: POST /v2/checkout/orders/{id}/capture
        """
        if str(self._client_id).upper() == "MOCK":
            # Simulate successful capture
            capture_id = f"MOCK-CAP-{provider_order_id}"
            raw = {
                "mock": True,
                "id": provider_order_id,
                "status": "COMPLETED",
                "purchase_units": [
                    {
                        "payments": {
                            "captures": [
                                {
                                    "id": capture_id,
                                    "status": "COMPLETED",
                                    "amount": {"value": "0.00", "currency_code": "USD"},
                                }
                            ]
                        }
                    }
                ],
            }
            return CaptureResult(
                success=True,
                transaction_id=capture_id,
                captured_amount=0.0,
                raw_response=raw,
            )

        token = self._get_access_token()
        if not token:
            return CaptureResult(success=False, error_message="Failed to obtain PayPal access token")

        try:
            response = requests.post(
                f"{self._base_url}/v2/checkout/orders/{provider_order_id}/capture",
                headers=self._auth_headers(),
                timeout=10,
            )
            try:
                data = response.json()
            except ValueError:
                data = {"message": response.text or "Invalid response from PayPal"}

            if response.status_code == 201 and data.get("status") == "COMPLETED":
                capture = (
                    data.get("purchase_units", [{}])[0]
                    .get("payments", {})
                    .get("captures", [{}])[0]
                )
                return CaptureResult(
                    success=True,
                    transaction_id=capture.get("id"),
                    captured_amount=float(capture.get("amount", {}).get("value", 0)),
                    raw_response=data,
                )

            logger.error("PayPal capture_payment failed: %s", data)
            return CaptureResult(
                success=False,
                error_message=data.get("message") or data.get("error_description") or "Capture failed",
            )

        except requests.RequestException as exc:
            logger.exception("PayPal capture_payment network error")
            return CaptureResult(success=False, error_message=str(exc))

    def refund_payment(
        self,
        capture_id: str,
        amount: float,
        currency: str,
        reason: str = "",
    ) -> RefundResult:
        """
        Refund a captured PayPal payment (full or partial).
        Maps to: POST /v2/payments/captures/{id}/refund
        """
        if str(self._client_id).upper() == "MOCK":
            refund_id = f"MOCK-REF-{capture_id}"
            raw = {
                "mock": True,
                "id": refund_id,
                "status": "COMPLETED",
                "amount": {"value": f"{amount:.2f}", "currency_code": currency.upper()},
            }
            return RefundResult(
                success=True,
                refund_id=refund_id,
                refunded_amount=amount,
                raw_response=raw,
            )

        token = self._get_access_token()
        if not token:
            return RefundResult(success=False, error_message="Failed to obtain PayPal access token")

        payload: dict = {}
        if amount > 0:
            payload["amount"] = {
                "value": f"{amount:.2f}",
                "currency_code": currency.upper(),
            }
        if reason:
            payload["note_to_payer"] = reason[:255]

        try:
            response = requests.post(
                f"{self._base_url}/v2/payments/captures/{capture_id}/refund",
                json=payload,
                headers=self._auth_headers(),
                timeout=10,
            )
            try:
                data = response.json()
            except ValueError:
                data = {"message": response.text or "Invalid response from PayPal"}

            if response.status_code == 201 and data.get("status") == "COMPLETED":
                return RefundResult(
                    success=True,
                    refund_id=data.get("id"),
                    refunded_amount=float(
                        data.get("amount", {}).get("value", amount)
                    ),
                    raw_response=data,
                )

            logger.error("PayPal refund_payment failed: %s", data)
            return RefundResult(
                success=False,
                error_message=data.get("message") or data.get("error_description") or "Refund failed",
            )

        except requests.RequestException as exc:
            logger.exception("PayPal refund_payment network error")
            return RefundResult(success=False, error_message=str(exc))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_access_token(self) -> Optional[str]:
        """
        Fetch or reuse a PayPal OAuth2 access token.
        Maps to: POST /v1/oauth2/token
        """
        # Prefer a shared cache if available so tokens are reused across workers.
        cache_key = f"paypal.access_token.{self._client_id}"
        try:
            from django.core.cache import cache  # type: ignore
        except Exception:
            cache = None

        # 1) Check process-local cache
        if self._access_token:
            return self._access_token

        # 2) Check Django cache (shared between workers)
        if cache is not None:
            token = cache.get(cache_key)
            if token:
                self._access_token = token
                return self._access_token

        try:
            response = requests.post(
                f"{self._base_url}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en_US",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                auth=(self._client_id, self._client_secret),
                timeout=10,
            )
            try:
                data = response.json()
            except ValueError:
                data = {"error_description": response.text or "Invalid response from PayPal"}

            if response.status_code != 200:
                logger.error("PayPal OAuth token request failed: %s", data)
                return None

            token = data.get("access_token")
            expires_in = int(data.get("expires_in", 0))

            if token:
                self._access_token = token
                # Cache with a small safety margin if cache is available
                if cache is not None and expires_in > 60:
                    cache.set(cache_key, token, timeout=max(expires_in - 30, 30))

            return self._access_token

        except requests.RequestException:
            logger.exception("PayPal OAuth token request failed")
            return None

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
