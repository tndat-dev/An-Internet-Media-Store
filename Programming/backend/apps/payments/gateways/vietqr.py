import logging
from dataclasses import dataclass
from decimal import Decimal
import base64

import requests
from django.conf import settings

from apps.payments.gateways.base import QRCodeResult
from apps.payments.models import PaymentTransaction
from apps.payments.gateways.token_manager import VietQRTokenManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VietQRGenerateResponse:
    """Response from VietQR generate QR endpoint"""

    qr_code: str
    qr_link: str
    content: str
    transaction_reference_id: str
    transaction_id: str
    bank_account: str
    bank_code: str
    user_bank_name: str
    amount: Decimal
    order_id: str


# /*
#  * SOLID Review
#  * Principle: SRP/DIP
#  * Reason: VietQRGateway handles token retrieval, settings access, HTTP requests, provider response parsing, and status lookup against PaymentTransaction.
#  * Impact: Gateway tests require external configuration and ORM state, and changing token/status behavior can affect QR generation code.
#  * Improvement: Keep provider HTTP mapping here but inject token/config/status collaborators and return DTOs without ORM lookup.
#  */
class VietQRGateway:
    """
    VietQR HTTP gateway for real QR code generation.

    Coupling Level:
    - Data Coupling: Returns defined QRCodeResult DTO
    - Data Coupling: Receives order_id, amount, and payment_id only
    - Data Coupling with VietQRTokenManager (token service)
    - Data Coupling with settings (config only)

    Cohesion Level:
    - Functional Cohesion: QR generation and VietQR integration only

    Reason:
    Gateway encapsulates all VietQR HTTP communication details.
    Service layer does not know about token management or HTTP retries.
    """

    provider_name = "VIETQR"

    def __init__(self, token_manager: VietQRTokenManager | None = None):
        self.token_manager = token_manager or VietQRTokenManager()
        self.base_url = settings.VIETQR_BASE_URL
        self.bank_code = settings.VIETQR_BANK_CODE
        self.bank_account = settings.VIETQR_BANK_ACCOUNT
        self.bank_account_name = settings.VIETQR_USER_BANK_NAME
        self.timeout = getattr(settings, "VIETQR_REQUEST_TIMEOUT", 10)

    def create_qr_code(
        self,
        *,
        order_id: str,
        amount: Decimal,
        payment_id: int,
    ) -> QRCodeResult:
        """
        Create VietQR QR code.

        Args:
            order_id: Original order ID from invoice
            amount: Payment amount in VND
            payment_id: Database payment transaction ID (for short reference)

        Returns:
            QRCodeResult with VietQR payload/link and transaction reference

        Raises:
            requests.RequestException: If VietQR API fails
        """
        # Generate short order ID reference (max 13 chars, alphanumeric).
        short_order_id = self._generate_short_order_id(payment_id)
        content = short_order_id

        token = self.token_manager.get_token()

        payload = {
            "bankCode": self.bank_code,
            "bankAccount": self.bank_account,
            "userBankName": self.bank_account_name,
            "content": content,
            "qrType": 0,  # Dynamic QR
            "amount": int(Decimal(amount)),
            "orderId": short_order_id,
            "transType": "C",  # Credit (receive)
        }

        try:
            response = requests.post(
                f"{self.base_url}/vqr/api/qr/generate-customer",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"VietQR QR generation failed: {e}")
            raise

        data = response.json()
        if data.get("status") == "FAILED":
            raise requests.RequestException(data.get("message", "VietQR QR generation failed"))

        # Parse response
        qr_response = VietQRGenerateResponse(
            qr_code=data["qrCode"],
            qr_link=data.get("qrLink", ""),
            content=data.get("content") or content,
            transaction_reference_id=data.get("transactionRefId", ""),
            transaction_id=data.get("transactionId", ""),
            bank_account=data.get("bankAccount", self.bank_account),
            bank_code=data.get("bankCode", self.bank_code),
            user_bank_name=data.get("userBankName", self.bank_account_name),
            amount=Decimal(data.get("amount", amount)),
            order_id=data.get("orderId") or short_order_id,
        )

        # Generate QR image URL: use qrLink from API, or convert EMV string to data URL
        qr_image_url = qr_response.qr_link or self._qr_code_to_data_url(qr_response.qr_code)

        return QRCodeResult(
            transaction_reference=qr_response.content,
            qr_payload=qr_response.qr_code,
            qr_image_url=qr_image_url,
            provider_metadata={
                "transaction_reference_id": qr_response.transaction_reference_id,
                "transaction_id": qr_response.transaction_id,
                "bank_account": qr_response.bank_account,
                "bank_code": qr_response.bank_code,
                "user_bank_name": qr_response.user_bank_name,
                "content": qr_response.content,
                "amount": self._format_amount(qr_response.amount),
                "order_id": qr_response.order_id,
                "qr_link": qr_response.qr_link,
                "qr_code": qr_response.qr_code,
                "raw_response": data,
            },
        )

    def request_test_callback(
        self,
        *,
        bank_account: str,
        content: str,
        amount,
        bank_code: str,
        trans_type: str = "C",
        amount_format: str = "number",
        raw_qr_fields: dict | None = None,
    ) -> dict:
        """
        Ask VietQR sandbox to simulate a paid transaction for a generated QR.
        """
        token_info = self.token_manager.get_token_info()
        token = token_info["token"]
        url = f"{self.base_url}/vqr/bank/api/test/transaction-callback"
        amount_decimal = Decimal(str(amount))
        amount_value = str(amount) if amount_format == "string" else int(amount_decimal)

        payload = {
            "bankAccount": str(bank_account),
            "content": str(content),
            "amount": amount_value,
            "bankCode": str(bank_code),
            "transType": str(trans_type),
        }

        try:
            logger.info("VietQR test callback url=%s", url)
            logger.info(
                "VietQR test callback token_exp=%s seconds_remaining=%s",
                token_info.get("exp"),
                token_info.get("seconds_remaining"),
            )
            logger.info("VietQR test callback payload=%s", payload)
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )

            # Always attempt to parse response body; don't raise on HTTP error
            try:
                response_body = response.json()
            except ValueError:
                response_body = {"raw": response.text}

            logger.info("VietQR test callback status=%s", response.status_code)
            logger.info("VietQR test callback response=%s", response_body)

            # If HTTP error statuses (400+) occur, return structured error
            if response.status_code >= 400:
                return {
                    "success": False,
                    "sandbox_only": True,
                    "variant": amount_format,
                    "code": "VIETQR_HTTP_ERROR",
                    "status_code": response.status_code,
                    "error": "VietQR rejected test callback request.",
                    "details": response_body,
                    "payload": payload,
                    "raw_qr_fields": raw_qr_fields or {},
                    "token_exp": token_info.get("exp"),
                    "seconds_remaining": token_info.get("seconds_remaining"),
                }

            # If provider responded with status FAILED inside 200 OK
            if isinstance(response_body, dict) and response_body.get("status") == "FAILED":
                return {
                    "success": False,
                    "sandbox_only": True,
                    "variant": amount_format,
                    "code": "VIETQR_FAILED",
                    "status_code": response.status_code,
                    "error": response_body.get("message", "VietQR test callback failed."),
                    "details": response_body,
                    "payload": payload,
                    "raw_qr_fields": raw_qr_fields or {},
                    "token_exp": token_info.get("exp"),
                    "seconds_remaining": token_info.get("seconds_remaining"),
                }

            # Success path: return parsed body and include payload for traceability
            result = response_body if isinstance(response_body, dict) else {"raw": response_body}
            result.update({
                "success": True,
                "sandbox_only": True,
                "variant": amount_format,
                "status_code": response.status_code,
                "payload": payload,
                "raw_qr_fields": raw_qr_fields or {},
                "token_exp": token_info.get("exp"),
                "seconds_remaining": token_info.get("seconds_remaining"),
            })
            return result

        except requests.exceptions.Timeout:
            logger.error("VietQR test callback request timed out. payload=%s", payload)
            return {
                "success": False,
                "sandbox_only": True,
                "variant": amount_format,
                "code": "VIETQR_TIMEOUT",
                "error": "VietQR test callback request timed out.",
                "payload": payload,
                "raw_qr_fields": raw_qr_fields or {},
                "token_exp": token_info.get("exp"),
                "seconds_remaining": token_info.get("seconds_remaining"),
            }
        except requests.exceptions.RequestException as exc:
            logger.error("VietQR test callback request error: %s payload=%s", exc, payload)
            return {
                "success": False,
                "sandbox_only": True,
                "variant": amount_format,
                "code": "VIETQR_REQUEST_ERROR",
                "error": str(exc),
                "payload": payload,
                "raw_qr_fields": raw_qr_fields or {},
                "token_exp": token_info.get("exp"),
                "seconds_remaining": token_info.get("seconds_remaining"),
            }

    def _generate_short_order_id(self, payment_id: int) -> str:
        """Generate ≤13 char order ID: AIMS{payment_id}"""
        short = f"AIMS{payment_id}"
        if len(short) > 13:
            # Fallback: truncate (shouldn't happen with reasonable IDs)
            short = short[:13]
        return short

    def _format_amount(self, amount: Decimal) -> str:
        """Format VND amount for VietQR without a decimal suffix."""
        amount = Decimal(amount)
        if amount == amount.to_integral_value():
            return str(int(amount))
        return format(amount.normalize(), "f")

    def _qr_code_to_data_url(self, qr_code_string: str) -> str:
        """
        Convert VietQR EMV QR code string to image data URL.
        Uses qrcode library to generate PNG from EMV string.
        Returns data:image/png;base64,... URL for direct rendering in img tags.
        """
        try:
            import qrcode
            from io import BytesIO

            # Generate QR image from EMV string
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_code_string)
            qr.make(fit=True)

            # Create PIL image
            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to PNG bytes
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_bytes = buffer.getvalue()

            # Encode to base64 and create data URL
            b64_str = base64.b64encode(img_bytes).decode('utf-8')
            return f"data:image/png;base64,{b64_str}"
        except Exception as e:
            logger.error(f"Failed to convert QR code to image: {e}")
            return ""

    def check_status(self, *, transaction_reference: str) -> str:
        """
        Mock status check (real implementation would call VietQR status endpoint).
        Backend state machine determines actual status.
        """
        # Status is managed by backend transaction model, not queried from VietQR
        try:
            payment = PaymentTransaction.objects.get(transaction_reference=transaction_reference)
            return payment.status
        except PaymentTransaction.DoesNotExist:
            return "PENDING"
