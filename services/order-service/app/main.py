"""Order aggregate owner and OrderCreated transactional-outbox producer."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import ssl
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx
import psycopg
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import TopicPartition
from fastapi import FastAPI, Header, HTTPException

from app.observability import install_observability
from app.shipping import DEFAULT_SHIPPING_POLICY
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("aims.order")

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS order_service;
CREATE TABLE IF NOT EXISTS order_service.orders (
  order_id uuid PRIMARY KEY, order_token uuid UNIQUE NOT NULL, cancel_token uuid UNIQUE NOT NULL,
  cart_token text NOT NULL, status text NOT NULL, total_amount numeric(14,2) NOT NULL,
  items jsonb NOT NULL, delivery_info jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(), processed_by text, processed_at timestamptz,
  rejection_reason text NOT NULL DEFAULT '', refund_summary jsonb
);
ALTER TABLE order_service.orders ADD COLUMN IF NOT EXISTS processed_by text;
ALTER TABLE order_service.orders ADD COLUMN IF NOT EXISTS processed_at timestamptz;
ALTER TABLE order_service.orders ADD COLUMN IF NOT EXISTS rejection_reason text NOT NULL DEFAULT '';
ALTER TABLE order_service.orders ADD COLUMN IF NOT EXISTS refund_summary jsonb;
CREATE TABLE IF NOT EXISTS order_service.outbox_events (
  id bigserial PRIMARY KEY, topic text NOT NULL, message_key text NOT NULL,
  payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz
);
CREATE INDEX IF NOT EXISTS order_outbox_unpublished ON order_service.outbox_events(id) WHERE published_at IS NULL;
"""


class ConfirmRequest(BaseModel):
    orderId: uuid.UUID


class DeliveryInput(BaseModel):
    customerName: str = Field(min_length=1, max_length=255)
    phoneNumber: str = Field(min_length=8, max_length=30)
    email: str = Field(min_length=3, max_length=255)
    deliveryProvince: str = Field(min_length=1, max_length=100)
    deliveryAddress: str = Field(min_length=1, max_length=500)
    deliveryMethod: str = Field(default="STANDARD", pattern="^(STANDARD|EXPRESS)$")
    deliveryInstructions: str = Field(default="", max_length=1000)

    @field_validator("customerName", "deliveryProvince", "deliveryAddress")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank")
        return normalized

    @field_validator("phoneNumber")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"\+?[0-9][0-9 .()-]{7,28}", normalized):
            raise ValueError("Enter a valid phone number")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized


class DeliveryPreviewInput(BaseModel):
    province: str = ""
    deliveryMethod: str = Field(default="STANDARD", pattern="^(STANDARD|EXPRESS)$")


class RejectOrderInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ManualRefundInput(BaseModel):
    note: str = Field(default="", max_length=500)


VAT_RATE = Decimal("0.10")
MONEY = Decimal("0.01")


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def calculate_delivery_fee(province: str, weight_kg: Decimal, order_value: Decimal) -> Decimal:
    """Compatibility boundary for callers using a precomputed weight."""
    try:
        return DEFAULT_SHIPPING_POLICY.fee(province, weight_kg, order_value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"deliveryProvince": str(error)}) from error


def invoice_totals(items: list[dict[str, Any]], delivery_fee: Decimal = Decimal("0")) -> dict[str, str]:
    subtotal = money(sum((Decimal(str(item["unitPrice"])) * int(item["quantity"]) for item in items), Decimal("0")))
    vat = money(subtotal * VAT_RATE)
    total_incl_vat = money(subtotal + vat)
    final_total = money(total_incl_vat + delivery_fee)
    return {
        "subtotalExclVat": f"{subtotal:.2f}",
        "vatAmount": f"{vat:.2f}",
        "totalInclVat": f"{total_incl_vat:.2f}",
        "deliveryFee": f"{money(delivery_fee):.2f}",
        "totalAmountToPay": f"{final_total:.2f}",
    }


def total_weight(items: list[dict[str, Any]]) -> Decimal:
    return DEFAULT_SHIPPING_POLICY.weight_strategy.chargeable_weight(items)


async def require_product_manager(authorization: str | None) -> dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication is required")
    auth_url = os.getenv("AUTH_SERVICE_URL", "http://auth-service.production.svc.cluster.local:8000").rstrip("/")
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(f"{auth_url}/api/auth/me/", headers={"Authorization": authorization})
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    user = response.json()
    if not set(user.get("roles", [])) & {"PRODUCT_MANAGER", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Product Manager role is required")
    return user


async def request_refund(order_id: str, reason: str) -> dict[str, Any]:
    payment_url = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service.production.svc.cluster.local:8000").rstrip("/")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"{payment_url}/api/payments/orders/{order_id}/refund/", json={"reason": reason})
    if response.status_code not in {200, 202}:
        detail = response.json().get("detail", "Refund could not be started") if response.headers.get("content-type", "").startswith("application/json") else "Refund could not be started"
        raise HTTPException(status_code=502, detail=detail)
    return response.json()


async def add_order_lifecycle_event(
    connection: psycopg.AsyncConnection,
    row: dict[str, Any],
    event_type: str,
) -> None:
    event = {
        "eventId": str(uuid.uuid4()),
        "eventType": event_type,
        "eventVersion": 1,
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "aggregateId": str(row["order_id"]),
        "correlationId": str(row["order_id"]),
        "payload": {
            "status": row["status"],
            "items": [
                {"productId": item["productId"], "quantity": item["quantity"]}
                for item in row["items"]
            ],
            "email": (row.get("delivery_info") or {}).get("email", ""),
            "orderToken": str(row["order_token"]),
        },
    }
    await connection.execute(
        "INSERT INTO order_service.outbox_events(topic,message_key,payload) VALUES (%s,%s,%s)",
        ("aims.business.order.lifecycle.v1", str(row["order_id"]), Jsonb(event)),
    )


def ssl_context() -> ssl.SSLContext | None:
    paths = [os.getenv("KAFKA_TLS_CERT", "/var/run/aims-kafka/user.crt"), os.getenv("KAFKA_TLS_KEY", "/var/run/aims-kafka/user.key"), os.getenv("KAFKA_TLS_CA", "/var/run/aims-kafka-ca/ca.crt")]
    if not all(os.path.exists(path) for path in paths):
        return None
    context = ssl.create_default_context(cafile=paths[2])
    context.load_cert_chain(paths[0], paths[1])
    return context


class OrderRuntime:
    def __init__(self) -> None:
        self.database_url = os.getenv("ORDER_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
        self.producer: AIOKafkaProducer | None = None
        self.consumer: AIOKafkaConsumer | None = None
        self.outbox_task: asyncio.Task | None = None
        self.payment_task: asyncio.Task | None = None
        self.database_ready = False
        self.kafka_ready = False

    async def start(self) -> None:
        if self.database_url:
            async with await psycopg.AsyncConnection.connect(self.database_url) as connection:
                await connection.execute("SELECT pg_advisory_xact_lock(hashtext('aims-order-schema-v1'))")
                await connection.execute(SCHEMA_SQL)
            self.database_ready = True
        bootstrap, tls = os.getenv("KAFKA_BOOTSTRAP_SERVERS", ""), ssl_context()
        if bootstrap and tls:
            self.producer = AIOKafkaProducer(bootstrap_servers=bootstrap, security_protocol="SSL", ssl_context=tls, acks="all", enable_idempotence=True)
            self.consumer = AIOKafkaConsumer(
                os.getenv("KAFKA_PAYMENT_TOPIC", "aims.business.payment.completed.v1"),
                bootstrap_servers=bootstrap,
                security_protocol="SSL",
                ssl_context=tls,
                group_id=os.getenv("KAFKA_PAYMENT_CONSUMER_GROUP", "aims.order-service.v1"),
                enable_auto_commit=False,
                auto_offset_reset="earliest",
                value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            )
            await self.producer.start()
            await self.consumer.start()
            self.kafka_ready = True
            self.outbox_task = asyncio.create_task(self.publish_outbox())
            self.payment_task = asyncio.create_task(self.consume_payments())

    async def stop(self) -> None:
        for task in (self.outbox_task, self.payment_task):
            if task:
                task.cancel()
        await asyncio.gather(*(task for task in (self.outbox_task, self.payment_task) if task), return_exceptions=True)
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def connect(self) -> psycopg.AsyncConnection:
        if not self.database_url:
            raise HTTPException(status_code=503, detail="Order database unavailable")
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)

    async def publish_outbox(self) -> None:
        assert self.producer
        while True:
            try:
                async with await self.connect() as connection:
                    cursor = await connection.execute(
                        "SELECT id,topic,message_key,payload FROM order_service.outbox_events "
                        "WHERE published_at IS NULL ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
                    )
                    row = await cursor.fetchone()
                    if row:
                        await asyncio.wait_for(
                            self.producer.send_and_wait(row["topic"], json.dumps(row["payload"]).encode(), key=row["message_key"].encode()),
                            timeout=20,
                        )
                        await connection.execute("UPDATE order_service.outbox_events SET published_at=now() WHERE id=%s", (row["id"],))
                        self.kafka_ready = True
                if not row:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.kafka_ready = False
                logger.exception("Order outbox publisher failed; retrying")
                await asyncio.sleep(3)

    async def consume_payments(self) -> None:
        """Reconcile successful provider payments into the Order aggregate.

        All order-service replicas share one consumer group, and the guarded
        transition is idempotent, so an event retry cannot regress an order.
        """
        assert self.consumer is not None
        async for message in self.consumer:
            event = message.value
            if event.get("eventType") == "PaymentCompleted":
                try:
                    order_id = uuid.UUID(str(event.get("aggregateId", "")))
                    async with await self.connect() as connection:
                        await connection.execute(
                            "UPDATE order_service.orders SET status='PENDING_PROCESSING',updated_at=now() "
                            "WHERE order_id=%s AND status='PENDING_PAYMENT'",
                            (order_id,),
                        )
                except (ValueError, TypeError):
                    # Malformed events are not retried forever; contract tests
                    # and telemetry surface the producer fault.
                    pass
                except Exception:
                    self.kafka_ready = False
                    self.consumer.seek(TopicPartition(message.topic, message.partition), message.offset)
                    await asyncio.sleep(3)
                    continue
            await self.consumer.commit()
            self.kafka_ready = True


runtime = OrderRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await runtime.start()
    except Exception:
        pass
    yield
    await runtime.stop()


app = FastAPI(title="AIMS order-service", version="1.0.0", lifespan=lifespan)
install_observability(app)


def render_order(row: dict[str, Any]) -> dict[str, Any]:
    items = []
    for item in row["items"]:
        price = Decimal(str(item["unitPrice"]))
        line = price * item["quantity"]
        items.append({"orderItemId": item.get("cartItemId", str(uuid.uuid4())), "productId": item["productId"], "productTitle": item["productTitle"], "unitPrice": f"{money(price):.2f}", "quantity": item["quantity"], "lineAmountExclVat": f"{money(line):.2f}", "lineAmountInclVat": f"{money(line * (Decimal('1') + VAT_RATE)):.2f}"})
    delivery_info = row["delivery_info"]
    fee = Decimal(str((delivery_info or {}).get("shippingFee", "0")))
    invoice = invoice_totals(row["items"], fee) if delivery_info else None
    if invoice:
        invoice["invoiceId"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"aims:invoice:{row['order_id']}"))
    return {"orderId": str(row["order_id"]), "orderToken": str(row["order_token"]), "cancelToken": str(row["cancel_token"]), "status": row["status"], "totalAmount": invoice["totalAmountToPay"] if invoice else f"{money(row['total_amount']):.2f}", "items": items, "deliveryInfo": delivery_info, "invoice": invoice, "refundSummary": row.get("refund_summary"), "processedAt": row.get("processed_at").isoformat() if row.get("processed_at") else None, "processedBy": row.get("processed_by"), "rejectionReason": row.get("rejection_reason", ""), "createdAt": row["created_at"].isoformat(), "updatedAt": row["updated_at"].isoformat()}


async def fetch_order(column: str, value: uuid.UUID) -> dict[str, Any]:
    if column not in {"order_id", "order_token", "cancel_token"}:
        raise ValueError("invalid lookup")
    async with await runtime.connect() as connection:
        cursor = await connection.execute(f"SELECT * FROM order_service.orders WHERE {column}=%s", (value,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    return render_order(row)


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "order-service", "databaseReady": runtime.database_ready, "kafkaReady": runtime.kafka_ready}


@app.post("/api/orders/draft/", status_code=201)
async def draft_order(x_cart_token: str | None = Header(default=None)) -> dict[str, Any]:
    if not x_cart_token:
        raise HTTPException(status_code=400, detail="X-Cart-Token is required")
    cart_url = os.getenv("CART_SERVICE_URL", "http://cart-service.production.svc.cluster.local:8000")
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(f"{cart_url}/api/cart/", headers={"X-Cart-Token": x_cart_token})
    if response.status_code != 200 or not response.json().get("items"):
        raise HTTPException(status_code=409, detail="Cart is empty or unavailable")
    cart = response.json()
    if not cart.get("canPlaceOrder", False):
        raise HTTPException(status_code=409, detail={"cart": cart.get("stockErrors", [])})
    order_id, order_token, cancel_token = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with await runtime.connect() as connection:
        totals = invoice_totals(cart["items"])
        cursor = await connection.execute("INSERT INTO order_service.orders(order_id,order_token,cancel_token,cart_token,status,total_amount,items) VALUES (%s,%s,%s,%s,'PENDING_PAYMENT',%s,%s) RETURNING *", (order_id, order_token, cancel_token, x_cart_token, Decimal(totals["totalInclVat"]), Jsonb(cart["items"])))
        row = await cursor.fetchone()
    return render_order(row)


@app.post("/api/orders/{order_id}/delivery/")
async def delivery(order_id: uuid.UUID, payload: DeliveryInput) -> dict[str, Any]:
    info = payload.model_dump()
    current = await fetch_order("order_id", order_id)
    fee = calculate_delivery_fee(payload.deliveryProvince, total_weight(current["items"]), Decimal(invoice_totals(current["items"])["subtotalExclVat"]))
    info.update({"deliveryInfoId": str(uuid.uuid4()), "shippingFee": f"{fee:.2f}"})
    final_total = Decimal(invoice_totals(current["items"], fee)["totalAmountToPay"])
    async with await runtime.connect() as connection:
        cursor = await connection.execute("UPDATE order_service.orders SET delivery_info=%s,total_amount=%s,updated_at=now() WHERE order_id=%s RETURNING *", (Jsonb(info), final_total, order_id))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    return render_order(row)


@app.post("/api/orders/")
async def confirm(payload: ConfirmRequest) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        async with connection.transaction():
            cursor = await connection.execute("UPDATE order_service.orders SET status='PENDING_PAYMENT',updated_at=now() WHERE order_id=%s RETURNING *", (payload.orderId,))
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Order not found")
            event = {"eventId": str(uuid.uuid4()), "eventType": "OrderCreated", "eventVersion": 1, "occurredAt": datetime.now(timezone.utc).isoformat(), "aggregateId": str(row["order_id"]), "correlationId": str(row["order_id"]), "payload": {"totalAmount": str(row["total_amount"]), "currency": "VND", "items": [{"productId": item["productId"], "quantity": item["quantity"]} for item in row["items"]]}}
            await connection.execute("INSERT INTO order_service.outbox_events(topic,message_key,payload) VALUES (%s,%s,%s)", ("aims.business.order.created.v1", str(row["order_id"]), Jsonb(event)))
    return render_order(row)


@app.get("/api/orders/{token}/")
async def get_order(token: uuid.UUID) -> dict[str, Any]:
    try:
        return await fetch_order("order_token", token)
    except HTTPException:
        return await fetch_order("order_id", token)


@app.post("/api/orders/{order_id}/mark-paid/")
async def mark_paid(order_id: uuid.UUID) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        cursor = await connection.execute("UPDATE order_service.orders SET status='PENDING_PROCESSING',updated_at=now() WHERE order_id=%s AND status='PENDING_PAYMENT' RETURNING *", (order_id,))
        row = await cursor.fetchone()
        if not row:
            row = await (await connection.execute("SELECT * FROM order_service.orders WHERE order_id=%s", (order_id,))).fetchone()
    if not row: raise HTTPException(status_code=404, detail="Order not found")
    if row["status"] != "PENDING_PROCESSING":
        raise HTTPException(status_code=409, detail="Only pending-payment orders can be marked paid")
    return render_order(row)


@app.post("/api/orders/{order_id}/delivery/preview/")
async def delivery_preview(order_id: uuid.UUID, payload: DeliveryPreviewInput) -> dict[str, str]:
    order = await fetch_order("order_id", order_id)
    province = payload.province or (order.get("deliveryInfo") or {}).get("deliveryProvince", "")
    subtotal = Decimal(invoice_totals(order["items"])["subtotalExclVat"])
    fee = calculate_delivery_fee(province, total_weight(order["items"]), subtotal)
    return invoice_totals(order["items"], fee)


@app.get("/api/orders/{order_id}/invoice/")
async def invoice(order_id: uuid.UUID) -> dict[str, Any]:
    order = await fetch_order("order_id", order_id)
    if order["deliveryInfo"] is None: raise HTTPException(status_code=409, detail="Delivery information is required")
    totals = invoice_totals(order["items"], Decimal(str(order["deliveryInfo"].get("shippingFee", "0"))))
    return {"invoiceId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"aims:invoice:{order_id}")), "orderId": order["orderId"], "orderToken": order["orderToken"], "status": order["status"], "items": order["items"], "deliveryInfo": order["deliveryInfo"], **totals}


@app.post("/api/orders/{cancel_token}/cancel/")
async def cancel(cancel_token: uuid.UUID) -> dict[str, Any]:
    current = await fetch_order("cancel_token", cancel_token)
    if current["status"] != "PENDING_PROCESSING":
        raise HTTPException(status_code=409, detail="Only paid orders awaiting approval can be cancelled")
    refund = await request_refund(current["orderId"], "Customer cancelled order")
    async with await runtime.connect() as connection:
        async with connection.transaction():
            cursor = await connection.execute("UPDATE order_service.orders SET status='CANCELLED',refund_summary=%s,updated_at=now() WHERE cancel_token=%s AND status='PENDING_PROCESSING' RETURNING *", (Jsonb(refund), cancel_token))
            row = await cursor.fetchone()
            if row:
                await add_order_lifecycle_event(connection, row, "OrderCancelled")
    if not row: raise HTTPException(status_code=409, detail="Order state changed before cancellation")
    return render_order(row)


@app.get("/api/orders/manage/pending/")
async def pending_orders(page: int = 1, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    await require_product_manager(authorization)
    page = max(page, 1)
    async with await runtime.connect() as connection:
        count = (await (await connection.execute("SELECT count(*) AS count FROM order_service.orders WHERE status='PENDING_PROCESSING'")).fetchone())["count"]
        rows = await (await connection.execute("SELECT * FROM order_service.orders WHERE status='PENDING_PROCESSING' ORDER BY created_at ASC LIMIT 30 OFFSET %s", ((page - 1) * 30,))).fetchall()
    return {"count": count, "next": page + 1 if page * 30 < count else None, "previous": page - 1 if page > 1 else None, "results": [render_order(row) for row in rows]}


@app.get("/api/orders/manage/refunds/")
async def refund_orders(page: int = 1, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    await require_product_manager(authorization)
    page = max(page, 1)
    predicate = "status IN ('REJECTED','CANCELLED') AND refund_summary IS NOT NULL"
    async with await runtime.connect() as connection:
        count = (await (await connection.execute(f"SELECT count(*) AS count FROM order_service.orders WHERE {predicate}")).fetchone())["count"]
        rows = await (await connection.execute(f"SELECT * FROM order_service.orders WHERE {predicate} ORDER BY updated_at DESC LIMIT 30 OFFSET %s", ((page - 1) * 30,))).fetchall()
    return {"count": count, "next": page + 1 if page * 30 < count else None, "previous": page - 1 if page > 1 else None, "results": [render_order(row) for row in rows]}


@app.get("/api/orders/manage/{order_id}/")
async def manager_order(order_id: uuid.UUID, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    await require_product_manager(authorization)
    return await fetch_order("order_id", order_id)


@app.post("/api/orders/manage/{order_id}/approve/")
async def approve_order(order_id: uuid.UUID, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = await require_product_manager(authorization)
    async with await runtime.connect() as connection:
        async with connection.transaction():
            cursor = await connection.execute("UPDATE order_service.orders SET status='APPROVED',processed_by=%s,processed_at=now(),updated_at=now() WHERE order_id=%s AND status='PENDING_PROCESSING' RETURNING *", (user["username"], order_id))
            row = await cursor.fetchone()
            if row:
                await add_order_lifecycle_event(connection, row, "OrderApproved")
    if not row:
        raise HTTPException(status_code=409, detail="Only pending-processing orders can be approved")
    return render_order(row)


@app.post("/api/orders/manage/{order_id}/reject/")
async def reject_order(order_id: uuid.UUID, payload: RejectOrderInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = await require_product_manager(authorization)
    current = await fetch_order("order_id", order_id)
    if current["status"] != "PENDING_PROCESSING":
        raise HTTPException(status_code=409, detail="Only pending-processing orders can be rejected")
    refund = await request_refund(str(order_id), payload.reason)
    async with await runtime.connect() as connection:
        async with connection.transaction():
            cursor = await connection.execute("UPDATE order_service.orders SET status='REJECTED',processed_by=%s,processed_at=now(),rejection_reason=%s,refund_summary=%s,updated_at=now() WHERE order_id=%s AND status='PENDING_PROCESSING' RETURNING *", (user["username"], payload.reason, Jsonb(refund), order_id))
            row = await cursor.fetchone()
            if row:
                await add_order_lifecycle_event(connection, row, "OrderRejected")
    if not row:
        raise HTTPException(status_code=409, detail="Order state changed before rejection")
    return render_order(row)


@app.post("/api/orders/manage/{order_id}/mark-refunded/")
async def mark_order_refunded(order_id: uuid.UUID, payload: ManualRefundInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = await require_product_manager(authorization)
    async with await runtime.connect() as connection:
        cursor = await connection.execute("SELECT * FROM order_service.orders WHERE order_id=%s", (order_id,))
        current = await cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Order not found")
        summary = dict(current.get("refund_summary") or {})
        if summary.get("refundMethod") != "MANUAL_BANK_TRANSFER":
            raise HTTPException(status_code=409, detail="This order does not require a manual refund")
        summary.update({"refundStatus": "SUCCESS", "manualRefundNote": payload.note, "processedBy": user["username"], "processedAt": datetime.now(timezone.utc).isoformat()})
        row = await (await connection.execute("UPDATE order_service.orders SET refund_summary=%s,updated_at=now() WHERE order_id=%s RETURNING *", (Jsonb(summary), order_id))).fetchone()
    return render_order(row)
