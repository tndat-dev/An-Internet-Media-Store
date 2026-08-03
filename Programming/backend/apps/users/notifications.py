"""User-account email notifications.

Non-fatal by design (mirrors apps/orders/notifications): a mail failure is logged
and swallowed so it can never break account management. Callers fire these via
transaction.on_commit so mail is only sent once the change has persisted.

Initial/reset passwords travel ONLY through these emails — never stored in audit
detail, never returned in API responses, never logged.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _send(subject: str, body: str, recipient: str | None) -> None:
    if not recipient:
        logger.info("Skipping email '%s': no recipient address.", subject)
        return
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 - notifications must never break the flow
        logger.exception("Failed to send email '%s' to %s", subject, recipient)


def send_account_created(user, initial_password: str) -> None:
    body = (
        f"An AIMS account has been created for you.\n\n"
        f"Username: {user.username}\n"
        f"Temporary password: {initial_password}\n\n"
        "Please sign in and change your password from your profile."
    )
    _send("Your AIMS account has been created", body, user.email)


def send_password_reset(user, new_password: str) -> None:
    body = (
        f"Your AIMS password has been reset by an administrator.\n\n"
        f"New temporary password: {new_password}\n\n"
        "Please sign in and change it from your profile."
    )
    _send("Your AIMS password was reset", body, user.email)


def send_email_changed(user, old_email: str, new_email: str) -> None:
    body = (
        f"The email address on your AIMS account was changed from {old_email} to {new_email}. "
        "If you did not request this, contact an administrator immediately."
    )
    # Notify BOTH addresses (account-takeover safeguard).
    _send("Your AIMS account email was changed", body, old_email)
    _send("Your AIMS account email was changed", body, new_email)


def send_account_blocked(user) -> None:
    body = (
        "Your AIMS account has been blocked. You can no longer sign in. "
        "Contact an administrator if you believe this is a mistake."
    )
    _send("Your AIMS account has been blocked", body, user.email)
