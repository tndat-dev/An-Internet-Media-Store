import pytest
from django.core import mail
from django.test import override_settings

from apps.orders import notifications
from apps.orders.models import Order

from ._helpers import create_product, place_confirmed_order

pytestmark = pytest.mark.django_db


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_order_confirmation_email_goes_to_customer():
    product = create_product(barcode="NOTIF-001")
    order_id = place_confirmed_order(product, 1, "notif-confirm-token")
    order = Order.objects.select_related("delivery_info", "invoice").get(order_id=order_id)

    notifications.send_order_confirmation(order)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["a@example.com"]
    assert str(order_id) in mail.outbox[0].subject


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AIMS_MANAGER_NOTICE_EMAIL="ops@aims.local",
)
def test_manual_refund_notice_goes_to_manager():
    product = create_product(barcode="NOTIF-002")
    order_id = place_confirmed_order(product, 1, "notif-refund-token")
    order = Order.objects.get(order_id=order_id)

    notifications.send_manual_refund_notice(order, 198000)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["ops@aims.local"]
    assert "Manual refund" in mail.outbox[0].subject


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_notification_is_non_fatal_without_recipient():
    # An order with no delivery info must not raise when notifying.
    order = Order.objects.create()
    notifications.send_order_confirmation(order)  # should silently skip
    assert mail.outbox == []
