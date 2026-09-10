"""Order aggregate owner and OrderCreated transactional-outbox producer."""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
import psycopg
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI, Header, HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS order_service;
CREATE TABLE IF NOT EXISTS order_service.orders (
  order_id uuid PRIMARY KEY, order_token uuid UNIQUE NOT NULL, cancel_token uuid UNIQUE NOT NULL,
  cart_token text NOT NULL, status text NOT NULL, total_amount numeric(14,2) NOT NULL,
  items jsonb NOT NULL, delivery_info jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS order_service.outbox_events (
  id bigserial PRIMARY KEY, topic text NOT NULL, message_key text NOT NULL,
  payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz
);
CREATE INDEX IF NOT EXISTS order_outbox_unpublished ON order_service.outbox_events(id) WHERE published_at IS NULL;
"""


class ConfirmRequest(BaseModel):
    orderId: uuid.UUID


class DeliveryInput(BaseModel):
    customerName: str
    phoneNumber: str
    email: str
    deliveryProvince: str
    deliveryAddress: str
    deliveryMethod: str = "STANDARD"
    deliveryInstructions: str = ""


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
        self.outbox_task: asyncio.Task | None = None
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
            await self.producer.start()
            self.kafka_ready = True
            self.outbox_task = asyncio.create_task(self.publish_outbox())

    async def stop(self) -> None:
        if self.outbox_task:
            self.outbox_task.cancel()
            await asyncio.gather(self.outbox_task, return_exceptions=True)
        if self.producer:
            await self.producer.stop()

    async def connect(self) -> psycopg.AsyncConnection:
        if not self.database_url:
            raise HTTPException(status_code=503, detail="Order database unavailable")
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)

    async def publish_outbox(self) -> None:
        assert self.producer
        while True:
            async with await self.connect() as connection:
                cursor = await connection.execute("SELECT id,topic,message_key,payload FROM order_service.outbox_events WHERE published_at IS NULL ORDER BY id LIMIT 1")
                row = await cursor.fetchone()
                if row:
                    await self.producer.send_and_wait(row["topic"], json.dumps(row["payload"]).encode(), key=row["message_key"].encode())
                    await connection.execute("UPDATE order_service.outbox_events SET published_at=now() WHERE id=%s", (row["id"],))
                else:
                    await asyncio.sleep(1)


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


def render_order(row: dict[str, Any]) -> dict[str, Any]:
    items = []
    for item in row["items"]:
        price = Decimal(str(item["unitPrice"]))
        line = price * item["quantity"]
        items.append({"orderItemId": item.get("cartItemId", str(uuid.uuid4())), "productId": item["productId"], "productTitle": item["productTitle"], "unitPrice": str(price), "quantity": item["quantity"], "lineAmountExclVat": str(line), "lineAmountInclVat": str(line)})
    return {"orderId": str(row["order_id"]), "orderToken": str(row["order_token"]), "cancelToken": str(row["cancel_token"]), "status": row["status"], "totalAmount": str(row["total_amount"]), "items": items, "deliveryInfo": row["delivery_info"], "invoice": None, "refundSummary": None, "createdAt": row["created_at"].isoformat(), "updatedAt": row["updated_at"].isoformat()}


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
    order_id, order_token, cancel_token = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with await runtime.connect() as connection:
        cursor = await connection.execute("INSERT INTO order_service.orders(order_id,order_token,cancel_token,cart_token,status,total_amount,items) VALUES (%s,%s,%s,%s,'PENDING_PAYMENT',%s,%s) RETURNING *", (order_id, order_token, cancel_token, x_cart_token, Decimal(cart["subtotalExclVat"]), Jsonb(cart["items"])))
        row = await cursor.fetchone()
    return render_order(row)


@app.post("/api/orders/{order_id}/delivery/")
async def delivery(order_id: uuid.UUID, payload: DeliveryInput) -> dict[str, Any]:
    info = payload.model_dump()
    info.update({"deliveryInfoId": str(uuid.uuid4()), "shippingFee": "0.00"})
    async with await runtime.connect() as connection:
        cursor = await connection.execute("UPDATE order_service.orders SET delivery_info=%s,updated_at=now() WHERE order_id=%s RETURNING *", (Jsonb(info), order_id))
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
        cursor = await connection.execute("UPDATE order_service.orders SET status='PENDING_PROCESSING',updated_at=now() WHERE order_id=%s RETURNING *", (order_id,))
        row = await cursor.fetchone()
    if not row: raise HTTPException(status_code=404, detail="Order not found")
    return render_order(row)


@app.post("/api/orders/{order_id}/delivery/preview/")
async def delivery_preview(order_id: uuid.UUID) -> dict[str, str]:
    order = await fetch_order("order_id", order_id)
    subtotal = Decimal(order["totalAmount"])
    return {"subtotalExclVat": str(subtotal), "vatAmount": "0.00", "totalInclVat": str(subtotal), "deliveryFee": "0.00", "totalAmountToPay": str(subtotal)}


@app.get("/api/orders/{order_id}/invoice/")
async def invoice(order_id: uuid.UUID) -> dict[str, Any]:
    order = await fetch_order("order_id", order_id)
    if order["deliveryInfo"] is None: raise HTTPException(status_code=409, detail="Delivery information is required")
    subtotal = order["totalAmount"]
    return {"invoiceId": str(uuid.uuid4()), "orderId": order["orderId"], "orderToken": order["orderToken"], "status": order["status"], "items": order["items"], "deliveryInfo": order["deliveryInfo"], "subtotalExclVat": subtotal, "vatAmount": "0.00", "totalInclVat": subtotal, "deliveryFee": "0.00", "totalAmountToPay": subtotal}


@app.post("/api/orders/{cancel_token}/cancel/")
async def cancel(cancel_token: uuid.UUID) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        cursor = await connection.execute("UPDATE order_service.orders SET status='CANCELLED',updated_at=now() WHERE cancel_token=%s AND status IN ('PENDING_PAYMENT','PENDING_PROCESSING') RETURNING *", (cancel_token,))
        row = await cursor.fetchone()
    if not row: raise HTTPException(status_code=404, detail="Cancellable order not found")
    return render_order(row)
