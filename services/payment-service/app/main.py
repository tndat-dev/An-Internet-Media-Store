"""Payment state machine consuming InventoryReserved and publishing PaymentCompleted."""

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

import psycopg
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS payment_service;
CREATE TABLE IF NOT EXISTS payment_service.payments (
  payment_id uuid PRIMARY KEY, order_id text UNIQUE NOT NULL, amount numeric(14,2) NOT NULL,
  currency text NOT NULL, provider text NOT NULL, status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS payment_service.processed_events(event_id text PRIMARY KEY, processed_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS payment_service.outbox_events(
  id bigserial PRIMARY KEY, topic text NOT NULL, message_key text NOT NULL, payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz
);
"""


class PaymentRequest(BaseModel):
    orderId: str = Field(min_length=1)
    amount: Decimal = Field(ge=0)
    currency: str = "VND"
    provider: str = "VIETQR"


class VietQRRequest(BaseModel):
    order_id: str
    amount: Decimal = Field(ge=0)


class CallbackRequest(BaseModel):
    transaction_id: uuid.UUID


def tls_context() -> ssl.SSLContext | None:
    cert, key, ca = (os.getenv("KAFKA_TLS_CERT", "/var/run/aims-kafka/user.crt"), os.getenv("KAFKA_TLS_KEY", "/var/run/aims-kafka/user.key"), os.getenv("KAFKA_TLS_CA", "/var/run/aims-kafka-ca/ca.crt"))
    if not all(os.path.exists(path) for path in (cert, key, ca)):
        return None
    context = ssl.create_default_context(cafile=ca)
    context.load_cert_chain(cert, key)
    return context


class PaymentRuntime:
    def __init__(self) -> None:
        self.database_url = os.getenv("PAYMENT_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
        self.consumer: AIOKafkaConsumer | None = None
        self.producer: AIOKafkaProducer | None = None
        self.tasks: list[asyncio.Task] = []
        self.database_ready = False
        self.kafka_ready = False

    async def connect(self) -> psycopg.AsyncConnection:
        if not self.database_url:
            raise HTTPException(status_code=503, detail="Payment database unavailable")
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)

    async def start(self) -> None:
        if self.database_url:
            async with await psycopg.AsyncConnection.connect(self.database_url) as connection:
                await connection.execute("SELECT pg_advisory_xact_lock(hashtext('aims-payment-schema-v1'))")
                await connection.execute(SCHEMA_SQL)
            self.database_ready = True
        bootstrap, tls = os.getenv("KAFKA_BOOTSTRAP_SERVERS", ""), tls_context()
        if bootstrap and tls:
            common = {"bootstrap_servers": bootstrap, "security_protocol": "SSL", "ssl_context": tls}
            self.consumer = AIOKafkaConsumer(os.getenv("KAFKA_CONSUMER_TOPIC", "aims.business.inventory.reserved.v1"), group_id="aims.payment-service.v1", enable_auto_commit=False, value_deserializer=lambda value: json.loads(value.decode()), **common)
            self.producer = AIOKafkaProducer(acks="all", enable_idempotence=True, **common)
            await self.producer.start(); await self.consumer.start()
            self.kafka_ready = True
            self.tasks = [asyncio.create_task(self.consume()), asyncio.create_task(self.publish_outbox())]

    async def stop(self) -> None:
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.consumer: await self.consumer.stop()
        if self.producer: await self.producer.stop()

    async def consume(self) -> None:
        assert self.consumer
        async for message in self.consumer:
            event = message.value
            if event.get("eventType") == "InventoryReserved" and self.database_url:
                async with await self.connect() as connection:
                    async with connection.transaction():
                        prior = await connection.execute("SELECT 1 FROM payment_service.processed_events WHERE event_id=%s", (event["eventId"],))
                        if not await prior.fetchone():
                            payload = event.get("payload", {})
                            await connection.execute("INSERT INTO payment_service.payments(payment_id,order_id,amount,currency,provider,status) VALUES (%s,%s,%s,%s,'VIETQR','AWAITING_PAYMENT') ON CONFLICT(order_id) DO NOTHING", (uuid.uuid4(), event["aggregateId"], Decimal(str(payload.get("totalAmount", "0"))), payload.get("currency", "VND")))
                            await connection.execute("INSERT INTO payment_service.processed_events(event_id) VALUES (%s)", (event["eventId"],))
            await self.consumer.commit()

    async def publish_outbox(self) -> None:
        assert self.producer
        while True:
            async with await self.connect() as connection:
                cursor = await connection.execute("SELECT id,topic,message_key,payload FROM payment_service.outbox_events WHERE published_at IS NULL ORDER BY id LIMIT 1")
                row = await cursor.fetchone()
                if row:
                    await self.producer.send_and_wait(row["topic"], json.dumps(row["payload"]).encode(), key=row["message_key"].encode())
                    await connection.execute("UPDATE payment_service.outbox_events SET published_at=now() WHERE id=%s", (row["id"],))
                else: await asyncio.sleep(1)

    async def complete(self, payload: PaymentRequest) -> dict[str, Any]:
        payment_id = uuid.uuid4()
        event = {"eventId": str(uuid.uuid4()), "eventType": "PaymentCompleted", "eventVersion": 1, "occurredAt": datetime.now(timezone.utc).isoformat(), "aggregateId": payload.orderId, "correlationId": payload.orderId, "payload": {"paymentId": str(payment_id), "status": "COMPLETED", "amount": str(payload.amount), "currency": payload.currency}}
        async with await self.connect() as connection:
            async with connection.transaction():
                cursor = await connection.execute("INSERT INTO payment_service.payments(payment_id,order_id,amount,currency,provider,status) VALUES (%s,%s,%s,%s,%s,'COMPLETED') ON CONFLICT(order_id) DO UPDATE SET status='COMPLETED',updated_at=now() RETURNING *", (payment_id, payload.orderId, payload.amount, payload.currency, payload.provider))
                row = await cursor.fetchone()
                await connection.execute("INSERT INTO payment_service.outbox_events(topic,message_key,payload) VALUES ('aims.business.payment.completed.v1',%s,%s)", (payload.orderId, Jsonb(event)))
        return dict(row)

    async def create_pending(self, order_id: str, amount: Decimal) -> dict[str, Any]:
        async with await self.connect() as connection:
            cursor = await connection.execute("INSERT INTO payment_service.payments(payment_id,order_id,amount,currency,provider,status) VALUES (%s,%s,%s,'VND','VIETQR','PENDING') ON CONFLICT(order_id) DO UPDATE SET amount=EXCLUDED.amount,status='PENDING',updated_at=now() RETURNING *", (uuid.uuid4(), order_id, amount))
            return dict(await cursor.fetchone())

    async def get(self, payment_id: uuid.UUID) -> dict[str, Any] | None:
        async with await self.connect() as connection:
            cursor = await connection.execute("SELECT * FROM payment_service.payments WHERE payment_id=%s", (payment_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def complete_by_id(self, payment_id: uuid.UUID) -> dict[str, Any] | None:
        async with await self.connect() as connection:
            async with connection.transaction():
                cursor = await connection.execute("UPDATE payment_service.payments SET status='SUCCESS',updated_at=now() WHERE payment_id=%s RETURNING *", (payment_id,))
                row = await cursor.fetchone()
                if not row: return None
                event = {"eventId": str(uuid.uuid4()), "eventType": "PaymentCompleted", "eventVersion": 1, "occurredAt": datetime.now(timezone.utc).isoformat(), "aggregateId": row["order_id"], "correlationId": row["order_id"], "payload": {"paymentId": str(row["payment_id"]), "status": "COMPLETED", "amount": str(row["amount"]), "currency": row["currency"]}}
                await connection.execute("INSERT INTO payment_service.outbox_events(topic,message_key,payload) VALUES ('aims.business.payment.completed.v1',%s,%s)", (row["order_id"], Jsonb(event)))
                return dict(row)


runtime = PaymentRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try: await runtime.start()
    except Exception: pass
    yield
    await runtime.stop()


app = FastAPI(title="AIMS payment-service", version="1.0.0", lifespan=lifespan)


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "payment-service", "databaseReady": runtime.database_ready, "kafkaReady": runtime.kafka_ready}


@app.post("/api/payments/complete/", status_code=202)
async def complete_payment(payload: PaymentRequest) -> dict[str, Any]:
    row = await runtime.complete(payload)
    return {"paymentId": str(row["payment_id"]), "orderId": row["order_id"], "status": row["status"], "amount": str(row["amount"]), "currency": row["currency"], "provider": row["provider"]}


def vietqr_response(row: dict[str, Any]) -> dict[str, Any]:
    reference = f"AIMS-{str(row['payment_id']).split('-')[0].upper()}"
    return {"transaction_id": str(row["payment_id"]), "order_id": row["order_id"], "payment_method": "VIETQR", "status": row["status"], "amount": str(row["amount"]), "currency": row["currency"], "transaction_reference": reference, "qr_payload": f"vietqr://pay?ref={reference}&amount={row['amount']}", "qr_image_url": os.getenv("VIETQR_PLACEHOLDER_URL", "https://img.vietqr.io/image/MB-0000000000-compact2.png")}


@app.post("/api/payments/vietqr/qr-code/")
async def create_vietqr(payload: VietQRRequest) -> dict[str, Any]:
    return vietqr_response(await runtime.create_pending(payload.order_id, payload.amount))


@app.get("/api/payments/{transaction_id}/status/")
async def payment_status(transaction_id: uuid.UUID) -> dict[str, Any]:
    row = await runtime.get(transaction_id)
    if not row: raise HTTPException(status_code=404, detail="Payment not found")
    result = vietqr_response(row)
    return {key: result[key] for key in ("transaction_id", "order_id", "payment_method", "status", "amount", "currency", "transaction_reference")}


@app.post("/api/payments/vietqr/test-callback/")
async def test_callback(payload: CallbackRequest) -> dict[str, str]:
    row = await runtime.complete_by_id(payload.transaction_id)
    if not row: raise HTTPException(status_code=404, detail="Payment not found")
    return {"status": "SUCCESS", "message": "Sandbox payment completed"}
