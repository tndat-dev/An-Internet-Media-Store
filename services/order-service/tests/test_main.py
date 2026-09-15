import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import DeliveryInput, add_order_lifecycle_event, app, calculate_delivery_fee, invoice_totals, render_order
from app.shipping import AimsShippingPolicy


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "order-service"


def test_render_order_contract():
    now = datetime.now(timezone.utc)
    value = render_order({"order_id": uuid4(), "order_token": uuid4(), "cancel_token": uuid4(), "status": "PENDING_PAYMENT", "total_amount": Decimal("20"), "items": [{"productId": "p", "productTitle": "Book", "unitPrice": "10", "quantity": 2}], "delivery_info": None, "created_at": now, "updated_at": now})
    assert value["items"][0]["lineAmountExclVat"] == "20.00"
    assert value["items"][0]["lineAmountInclVat"] == "22.00"


def test_invoice_totals_apply_vat_and_tax_exempt_delivery():
    totals = invoice_totals([{"unitPrice": "12000", "quantity": 1}], Decimal("22000"))
    assert totals == {
        "subtotalExclVat": "12000.00",
        "vatAmount": "1200.00",
        "totalInclVat": "13200.00",
        "deliveryFee": "22000.00",
        "totalAmountToPay": "35200.00",
    }


def test_delivery_fee_tariff_and_discount():
    assert calculate_delivery_fee("Ha Noi", Decimal("3"), Decimal("12000")) == Decimal("22000.00")
    assert calculate_delivery_fee("Da Nang", Decimal("1"), Decimal("12000")) == Decimal("32500.00")
    assert calculate_delivery_fee("Ha Noi", Decimal("3"), Decimal("100001")) == Decimal("0.00")


def test_shipping_policy_accepts_alternative_weight_strategy_without_changing_tariff():
    class FixedWeight:
        def chargeable_weight(self, items):
            assert items[0]["quantity"] == 1
            return Decimal("4")

    policy = AimsShippingPolicy(weight_strategy=FixedWeight())
    assert policy.calculate("Ha Noi", [{"quantity": 1}], Decimal("12000")) == Decimal("27000.00")


def test_delivery_input_rejects_invalid_contact_details():
    valid = {
        "customerName": "AIMS Buyer",
        "phoneNumber": "+84 912 345 678",
        "email": "buyer@example.test",
        "deliveryProvince": "Ha Noi",
        "deliveryAddress": "1 Dai Co Viet",
    }
    assert DeliveryInput.model_validate(valid).email == "buyer@example.test"
    for field, value in (("phoneNumber", "abc"), ("email", "not-an-email"), ("deliveryAddress", "   ")):
        invalid = {**valid, field: value}
        try:
            DeliveryInput.model_validate(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{field} should have been rejected")


def test_order_lifecycle_event_contains_inventory_and_notification_data():
    calls = []

    class Connection:
        async def execute(self, query, params):
            calls.append((query, params))

    row = {
        "order_id": uuid4(),
        "order_token": uuid4(),
        "status": "REJECTED",
        "items": [{"productId": "product-1", "quantity": 2}],
        "delivery_info": {"email": "buyer@example.test"},
    }
    asyncio.run(add_order_lifecycle_event(Connection(), row, "OrderRejected"))
    topic, key, envelope = calls[0][1]
    assert topic == "aims.business.order.lifecycle.v1"
    assert key == str(row["order_id"])
    assert envelope.obj["eventType"] == "OrderRejected"
    assert envelope.obj["payload"]["items"] == [{"productId": "product-1", "quantity": 2}]
