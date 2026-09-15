#!/usr/bin/env python3
"""Destructive synthetic acceptance test for the AIMS problem statement.

Run against the lab only. It creates three paid sandbox orders and one product,
then removes the product. AIMS_TEST_MANAGER_TOKEN must belong to a user carrying
PRODUCT_MANAGER; add ADMIN as well to exercise account administration.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal
from typing import Any


BASE = os.getenv("AIMS_BASE_URL", "http://10.1.16.234:31088").rstrip("/")
HOST = os.getenv("AIMS_HOST", "aims.lab")
MANAGER_TOKEN = os.getenv("AIMS_TEST_MANAGER_TOKEN", "").strip()
ADMIN_TOKEN = os.getenv("AIMS_TEST_ADMIN_TOKEN", MANAGER_TOKEN).strip()
RUN_ID = uuid.uuid4().hex[:10]
failures = 0
cleanup_users: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures
    if condition:
        print(f"PASS  {label}")
    else:
        failures += 1
        print(f"FAIL  {label}{': ' + detail if detail else ''}")


def request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    token: str = "",
    cart_token: str = "",
    expected: tuple[int, ...] = (200,),
) -> tuple[int, Any]:
    headers = {"Accept": "application/json", "Host": HOST, "X-Forwarded-For": f"198.18.1.{(len(path) % 200) + 1}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Token {token}"
    if cart_token:
        headers["X-Cart-Token"] = cart_token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    try:
        payload = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        payload = raw.decode(errors="replace")
    check(f"{method} {path} -> {expected}", status in expected, f"HTTP {status}, body={str(payload)[:300]}")
    return status, payload


def wait_for(label: str, probe, predicate, timeout: int = 45):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = probe()
        if predicate(last):
            check(label, True)
            return last
        time.sleep(1)
    check(label, False, str(last)[:300])
    return last


def public_and_identity_checks() -> None:
    _, health = request("GET", "/api/health/")
    check("API Gateway Redis limiter ready", health.get("redisRateLimiter") == "ready", str(health))
    _, catalog = request("GET", "/api/products/?scope=customer")
    check("Customer landing page is capped at 20 products", len(catalog.get("results", [])) <= 20)
    request("GET", "/api/products/?scope=customer&search=book&min_price=1&sort=price_asc")
    request("GET", "/api/search/?q=book&limit=10")
    _, config = request("GET", "/api/payments/config/")
    check("PayPal runtime configuration present", config.get("paypalConfigured") is True, str(config))
    check("VietQR runtime configuration present", config.get("vietqrConfigured") is True, str(config))

    username = f"accept-buyer-{RUN_ID}"
    email = f"accept-buyer-{RUN_ID}@example.test"
    password = f"Aims-{RUN_ID}-Pass!"
    _, registration = request("POST", "/api/auth/register/", {"username": username, "email": email, "password": password, "fullName": "AIMS Acceptance Buyer"})
    cleanup_users.append(registration.get("user", {}).get("userId", ""))
    roles = registration.get("user", {}).get("roles", [])
    check("Self-registration assigns CUSTOMER only", roles == ["CUSTOMER"], f"roles={roles}")
    request("POST", "/api/auth/register/", {"username": username, "email": email, "password": password}, expected=(400,))
    request("POST", "/api/auth/login/", {"username": email, "password": password})


def admin_checks() -> None:
    if not ADMIN_TOKEN:
        print("SKIP  administrator operations (AIMS_TEST_ADMIN_TOKEN is empty)")
        return
    username = f"accept-managed-{RUN_ID}"
    _, user = request("POST", "/api/admin/users/", {"username": username, "email": f"{username}@example.test", "fullName": "Managed Acceptance User", "roleNames": ["PRODUCT_MANAGER"]}, token=ADMIN_TOKEN, expected=(201,))
    user_id = user.get("userId", "")
    if not user_id:
        return
    cleanup_users.append(user_id)
    request("GET", f"/api/admin/users/?search={username}", token=ADMIN_TOKEN)
    request("POST", f"/api/admin/users/{user_id}/roles/", {"roleNames": ["CUSTOMER", "PRODUCT_MANAGER"]}, token=ADMIN_TOKEN)
    _, blocked = request("POST", f"/api/admin/users/{user_id}/status/", {"status": "BLOCKED"}, token=ADMIN_TOKEN)
    check("Administrator can block account", blocked.get("status") == "BLOCKED")
    request("POST", f"/api/admin/users/{user_id}/status/", {"status": "ACTIVE"}, token=ADMIN_TOKEN)
    request("POST", f"/api/admin/users/{user_id}/reset-password/", token=ADMIN_TOKEN, expected=(204,))


def checkout(product_id: str, action: str, expected_available: int) -> None:
    cart_token = f"accept-cart-{RUN_ID}-{action}"
    _, cart = request("POST", "/api/cart/items/", {"productId": product_id, "quantity": 1}, cart_token=cart_token)
    check(f"{action}: cart subtotal excludes VAT", Decimal(cart["subtotalExclVat"]) == Decimal("12000"))
    _, draft = request("POST", "/api/orders/draft/", {}, cart_token=cart_token, expected=(201,))
    order_id, order_token, cancel_token = draft["orderId"], draft["orderToken"], draft["cancelToken"]
    _, preview = request("POST", f"/api/orders/{order_id}/delivery/preview/", {"province": "Ha Noi", "deliveryMethod": "STANDARD"})
    check(f"{action}: VAT is 10%", Decimal(preview["vatAmount"]) == Decimal("1200"), str(preview))
    check(f"{action}: Ha Noi first 3kg fee", Decimal(preview["deliveryFee"]) == Decimal("22000"), str(preview))
    check(f"{action}: final payable total", Decimal(preview["totalAmountToPay"]) == Decimal("35200"), str(preview))
    invalid_delivery = {"customerName": "Buyer", "phoneNumber": "invalid", "email": "invalid", "deliveryProvince": "Ha Noi", "deliveryAddress": ""}
    request("POST", f"/api/orders/{order_id}/delivery/", invalid_delivery, expected=(422,))
    delivery = {"customerName": "AIMS Buyer", "phoneNumber": "+84 912 345 678", "email": f"buyer-{RUN_ID}@example.test", "deliveryProvince": "Ha Noi", "deliveryAddress": "1 Dai Co Viet", "deliveryMethod": "STANDARD", "deliveryInstructions": "synthetic acceptance test"}
    request("POST", f"/api/orders/{order_id}/delivery/", delivery)
    _, invoice = request("GET", f"/api/orders/{order_id}/invoice/")
    check(f"{action}: invoice preserves tax-exempt shipping", Decimal(invoice["totalAmountToPay"]) == Decimal(invoice["totalInclVat"]) + Decimal(invoice["deliveryFee"]), str(invoice))
    request("POST", "/api/orders/", {"orderId": order_id})
    wait_for(
        f"{action}: Kafka reserves stock",
        lambda: request("GET", f"/api/inventory/{product_id}")[1],
        lambda stock: stock.get("available") == expected_available - 1 and stock.get("reserved", 0) >= 1,
    )
    _, qr = request("POST", "/api/payments/vietqr/qr-code/", {"order_id": order_id, "amount": "1"})
    check(f"{action}: VietQR ignores tampered browser amount", Decimal(qr["amount"]) == Decimal("35200"), str(qr))
    check(f"{action}: VietQR returns scannable payload", bool(qr.get("qr_code") or qr.get("qr_payload")))
    request("POST", "/api/payments/vietqr/test-callback/", {"transaction_id": qr["transaction_id"]})
    wait_for(
        f"{action}: PaymentCompleted transitions order",
        lambda: request("GET", f"/api/orders/{order_token}/")[1],
        lambda order: order.get("status") == "PENDING_PROCESSING",
    )
    if action == "approve":
        request("POST", f"/api/orders/manage/{order_id}/approve/", {}, token=MANAGER_TOKEN)
    elif action == "cancel":
        _, cancelled = request("POST", f"/api/orders/{cancel_token}/cancel/", {})
        check("VietQR cancellation requires manual refund", cancelled.get("refundSummary", {}).get("refundStatus") == "MANUAL_REQUIRED", str(cancelled))
        request("POST", f"/api/orders/manage/{order_id}/mark-refunded/", {"note": "Acceptance test refund"}, token=MANAGER_TOKEN)
    else:
        _, rejected = request("POST", f"/api/orders/manage/{order_id}/reject/", {"reason": "Acceptance test rejection"}, token=MANAGER_TOKEN)
        check("VietQR rejection requires manual refund", rejected.get("refundSummary", {}).get("refundStatus") == "MANUAL_REQUIRED", str(rejected))
        request("POST", f"/api/orders/manage/{order_id}/mark-refunded/", {"note": "Acceptance test refund"}, token=MANAGER_TOKEN)
    expected_final = expected_available - 1 if action == "approve" else expected_available
    wait_for(
        f"{action}: lifecycle finalizes inventory",
        lambda: request("GET", f"/api/inventory/{product_id}")[1],
        lambda stock: stock.get("available") == expected_final and stock.get("reserved") == 0,
    )


def manager_product_and_order_checks() -> None:
    if not MANAGER_TOKEN:
        print("SKIP  product/order manager operations (AIMS_TEST_MANAGER_TOKEN is empty)")
        return
    payload = {
        "product_type": "BOOK", "title": f"AIMS Acceptance Book {RUN_ID}", "category": "Acceptance", "general_description": "Synthetic product", "height": "20", "width": "14", "length": "2", "weight": "0.5", "barcode": f"ACCEPT-{RUN_ID}", "image_url": "", "original_value": "10000", "current_price": "12000", "stock_quantity": 5, "status": "ACTIVE", "type_details": {"authors": "AIMS Test", "cover_type": "Paperback", "publisher": "HUST", "publication_date": "2026-09-15"},
    }
    invalid = {**payload, "title": f"Invalid price {RUN_ID}", "barcode": f"INVALID-{RUN_ID}", "current_price": "20000", "stock_quantity": 0}
    request("POST", "/api/products/", invalid, token=MANAGER_TOKEN, expected=(422,))
    _, product = request("POST", "/api/products/", payload, token=MANAGER_TOKEN, expected=(201,))
    product_id = product.get("product_id", "")
    if not product_id:
        return
    request("GET", f"/api/products/{product_id}/?scope=customer")
    request("GET", f"/api/products/histories/?product_id={product_id}", token=MANAGER_TOKEN)
    checkout(product_id, "approve", 5)
    checkout(product_id, "cancel", 4)
    checkout(product_id, "reject", 4)
    _, manager_product = request("GET", f"/api/products/{product_id}/", token=MANAGER_TOKEN)
    check("Catalog composes authoritative post-order stock", manager_product.get("stock_quantity") == 4, str(manager_product))
    update = {**payload, "stock_quantity": 0, "stock_adjustment_reason": "Acceptance test cleanup"}
    request("PATCH", f"/api/products/{product_id}/", update, token=MANAGER_TOKEN)
    _, deleted = request("POST", "/api/products/delete/", {"product_ids": [product_id]}, token=MANAGER_TOKEN)
    check("Zero-stock product is deleted", deleted[0].get("status") == "DELETED", str(deleted))
    _, history = request("GET", f"/api/products/histories/?product_id={product_id}", token=MANAGER_TOKEN)
    actions = {entry["action_type"] for entry in history}
    check("Product create/stock/delete history is queryable", {"CREATE", "STOCK_ADJUST", "DELETE"}.issubset(actions), str(actions))


def main() -> int:
    public_and_identity_checks()
    admin_checks()
    manager_product_and_order_checks()
    print("CLEANUP_KEYCLOAK_USER_IDS=" + ",".join(filter(None, cleanup_users)))
    if failures:
        print(f"ACCEPTANCE FAIL: {failures} assertion(s)")
        return 1
    print("ACCEPTANCE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
