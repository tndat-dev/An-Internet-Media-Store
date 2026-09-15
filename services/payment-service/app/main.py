"""Payment state machine consuming InventoryReserved and publishing PaymentCompleted."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import psycopg
import aio_pika
import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.observability import install_observability
from aiokafka.structs import TopicPartition
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

logger = logging.getLogger("aims.payment")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS payment_service;
CREATE TABLE IF NOT EXISTS payment_service.payments (
  payment_id uuid PRIMARY KEY, order_id text UNIQUE NOT NULL, amount numeric(14,2) NOT NULL,
  currency text NOT NULL, provider text NOT NULL, status text NOT NULL,
  provider_order_id text, capture_id text, provider_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE payment_service.payments ADD COLUMN IF NOT EXISTS provider_order_id text;
ALTER TABLE payment_service.payments ADD COLUMN IF NOT EXISTS capture_id text;
ALTER TABLE payment_service.payments ADD COLUMN IF NOT EXISTS provider_payload jsonb NOT NULL DEFAULT '{}'::jsonb;
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


class PayPalInitiateRequest(BaseModel):
    order_id: str = Field(min_length=1)
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str = "USD"
    return_url: str = Field(min_length=1)
    cancel_url: str = Field(min_length=1)
    description: str = ""


class PayPalCaptureRequest(BaseModel):
    provider_order_id: str = Field(min_length=1)
    internal_order_id: str | None = None


class PayPalRefundRequest(BaseModel):
    order_id: str = Field(min_length=1)
    capture_id: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    reason: str = "Customer cancelled order"


class OrderRefundRequest(BaseModel):
    reason: str = "Order cancelled or rejected"


def paypal_base_url() -> str:
    sandbox = os.getenv("PAYPAL_SANDBOX", "true").strip().lower() == "true"
    return "https://api-m.sandbox.paypal.com" if sandbox else "https://api-m.paypal.com"


async def paypal_access_token() -> str:
    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="PayPal credentials are unavailable")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{paypal_base_url()}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="PayPal authentication failed")
    return response.json()["access_token"]


async def order_invoice(order_id: str) -> dict[str, Any]:
    base = os.getenv("ORDER_SERVICE_URL", "http://order-service.production.svc.cluster.local:8000").rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{base}/api/orders/{order_id}/invoice/")
    if response.status_code != 200:
        raise HTTPException(status_code=409, detail="A completed invoice is required before payment")
    return response.json()


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
        self.rabbit_connection: Any = None
        self.rabbit_channel: Any = None
        self.task_exchange: Any = None
        self.payment_queue: Any = None
        self.database_ready = False
        self.kafka_ready = False
        self.rabbit_ready = False
        self.last_error: str | None = None

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
        await self.start_rabbit()
        bootstrap, tls = os.getenv("KAFKA_BOOTSTRAP_SERVERS", ""), tls_context()
        if bootstrap and tls:
            common = {"bootstrap_servers": bootstrap, "security_protocol": "SSL", "ssl_context": tls}
            self.consumer = AIOKafkaConsumer(os.getenv("KAFKA_CONSUMER_TOPIC", "aims.business.inventory.reserved.v1"), group_id="aims.payment-service.v1", enable_auto_commit=False, value_deserializer=lambda value: json.loads(value.decode()), **common)
            self.producer = AIOKafkaProducer(acks="all", enable_idempotence=True, **common)
            await self.producer.start(); await self.consumer.start()
            self.kafka_ready = True
            self.tasks.extend([asyncio.create_task(self.consume()), asyncio.create_task(self.publish_outbox())])

    async def start_rabbit(self) -> None:
        host = os.getenv("RABBITMQ_HOST", "").strip()
        username = os.getenv("RABBITMQ_USERNAME", "")
        password = os.getenv("RABBITMQ_PASSWORD", "")
        if not host or not username or not password:
            logger.warning("RabbitMQ disabled: application credentials are unavailable")
            return
        self.rabbit_connection = await aio_pika.connect_robust(
            host=host,
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            login=username,
            password=password,
            client_properties={"connection_name": "aims-payment-service"},
        )
        self.rabbit_channel = await self.rabbit_connection.channel()
        await self.rabbit_channel.set_qos(prefetch_count=20)
        # Topology is operator-owned. Avoid passive declarations so the app
        # needs only publish/consume permissions, not configure permission.
        self.task_exchange = await self.rabbit_channel.get_exchange("aims.tasks", ensure=False)
        self.payment_queue = await self.rabbit_channel.get_queue("payment.tasks", ensure=False)
        self.rabbit_ready = True
        self.tasks.append(asyncio.create_task(self.consume_payment_tasks()))

    async def stop(self) -> None:
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.consumer: await self.consumer.stop()
        if self.producer: await self.producer.stop()
        if self.rabbit_connection:
            await self.rabbit_connection.close()
        self.rabbit_ready = False

    async def consume(self) -> None:
        assert self.consumer
        async for message in self.consumer:
            event = message.value
            if event.get("eventType") == "InventoryReserved":
                try:
                    await self.publish_payment_task(event)
                except Exception as error:
                    self.last_error = str(error)
                    self.rabbit_ready = False
                    self.consumer.seek(
                        TopicPartition(message.topic, message.partition), message.offset
                    )
                    await asyncio.sleep(3)
                    continue
            await self.consumer.commit()

    async def publish_payment_task(self, event: dict[str, Any]) -> None:
        if not self.task_exchange:
            raise RuntimeError("RabbitMQ task exchange is unavailable")
        await self.task_exchange.publish(
            aio_pika.Message(
                body=json.dumps(event).encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
                message_id=event.get("eventId"),
                correlation_id=event.get("correlationId"),
            ),
            routing_key="payment.execute",
        )
        self.rabbit_ready = True

    async def consume_payment_tasks(self) -> None:
        assert self.payment_queue is not None
        async with self.payment_queue.iterator() as iterator:
            async for message in iterator:
                try:
                    async with message.process(requeue=False):
                        event = json.loads(message.body.decode("utf-8"))
                        await self.process_inventory_event(event)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Payment task rejected to DLQ")

    async def process_inventory_event(self, event: dict[str, Any]) -> None:
        if event.get("eventType") != "InventoryReserved" or not self.database_url:
            return
        async with await self.connect() as connection:
            async with connection.transaction():
                prior = await connection.execute(
                    "SELECT 1 FROM payment_service.processed_events WHERE event_id=%s",
                    (event["eventId"],),
                )
                if await prior.fetchone():
                    return
                payload = event.get("payload", {})
                await connection.execute(
                    "INSERT INTO payment_service.payments(payment_id,order_id,amount,currency,provider,status) VALUES (%s,%s,%s,%s,'VIETQR','AWAITING_PAYMENT') ON CONFLICT(order_id) DO NOTHING",
                    (
                        uuid.uuid4(),
                        event["aggregateId"],
                        Decimal(str(payload.get("totalAmount", "0"))),
                        payload.get("currency", "VND"),
                    ),
                )
                await connection.execute(
                    "INSERT INTO payment_service.processed_events(event_id) VALUES (%s)",
                    (event["eventId"],),
                )

    async def publish_outbox(self) -> None:
        assert self.producer
        while True:
            try:
                async with await self.connect() as connection:
                    cursor = await connection.execute(
                        "SELECT id,topic,message_key,payload FROM payment_service.outbox_events "
                        "WHERE published_at IS NULL ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
                    )
                    row = await cursor.fetchone()
                    if row:
                        await asyncio.wait_for(
                            self.producer.send_and_wait(row["topic"], json.dumps(row["payload"]).encode(), key=row["message_key"].encode()),
                            timeout=20,
                        )
                        await connection.execute("UPDATE payment_service.outbox_events SET published_at=now() WHERE id=%s", (row["id"],))
                        self.kafka_ready = True
                if not row:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.kafka_ready = False
                logger.exception("Payment outbox publisher failed; retrying")
                await asyncio.sleep(3)

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
            cursor = await connection.execute("INSERT INTO payment_service.payments(payment_id,order_id,amount,currency,provider,status) VALUES (%s,%s,%s,'VND','VIETQR','PENDING') ON CONFLICT(order_id) DO UPDATE SET amount=EXCLUDED.amount,currency='VND',provider='VIETQR',status='PENDING',provider_order_id=NULL,capture_id=NULL,provider_payload='{}'::jsonb,updated_at=now() RETURNING *", (uuid.uuid4(), order_id, amount))
            return dict(await cursor.fetchone())

    async def save_provider_payment(
        self,
        *,
        order_id: str,
        amount: Decimal,
        provider: str,
        status: str,
        provider_order_id: str | None = None,
        provider_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with await self.connect() as connection:
            cursor = await connection.execute(
                "INSERT INTO payment_service.payments(payment_id,order_id,amount,currency,provider,status,provider_order_id,provider_payload) VALUES (%s,%s,%s,'VND',%s,%s,%s,%s) ON CONFLICT(order_id) DO UPDATE SET amount=EXCLUDED.amount,currency='VND',provider=EXCLUDED.provider,status=EXCLUDED.status,provider_order_id=EXCLUDED.provider_order_id,provider_payload=EXCLUDED.provider_payload,capture_id=NULL,updated_at=now() RETURNING *",
                (uuid.uuid4(), order_id, amount, provider, status, provider_order_id, Jsonb(provider_payload or {})),
            )
            return dict(await cursor.fetchone())

    async def finish_provider_payment(self, provider_order_id: str, capture_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with await self.connect() as connection:
            async with connection.transaction():
                cursor = await connection.execute(
                    "UPDATE payment_service.payments SET status='SUCCESS',capture_id=%s,provider_payload=provider_payload || %s,updated_at=now() WHERE provider_order_id=%s RETURNING *",
                    (capture_id, Jsonb(payload), provider_order_id),
                )
                row = await cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Payment transaction not found")
                event = {"eventId": str(uuid.uuid4()), "eventType": "PaymentCompleted", "eventVersion": 1, "occurredAt": datetime.now(timezone.utc).isoformat(), "aggregateId": row["order_id"], "correlationId": row["order_id"], "payload": {"paymentId": str(row["payment_id"]), "status": "COMPLETED", "amount": str(row["amount"]), "currency": row["currency"]}}
                await connection.execute("INSERT INTO payment_service.outbox_events(topic,message_key,payload) VALUES ('aims.business.payment.completed.v1',%s,%s)", (row["order_id"], Jsonb(event)))
                return dict(row)

    async def update_provider_payload(self, payment_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        async with await self.connect() as connection:
            cursor = await connection.execute(
                "UPDATE payment_service.payments SET provider_payload=%s,updated_at=now() WHERE payment_id=%s RETURNING *",
                (Jsonb(payload), payment_id),
            )
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Payment not found")
            return dict(row)

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
install_observability(app)


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "payment-service", "databaseReady": runtime.database_ready, "kafkaReady": runtime.kafka_ready, "rabbitReady": runtime.rabbit_ready, "lastError": runtime.last_error}


@app.get("/api/payments/config/")
async def payment_config() -> dict[str, Any]:
    paypal_client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    vietqr_keys = ("VIETQR_USERNAME", "VIETQR_PASSWORD", "VIETQR_BANK_CODE", "VIETQR_BANK_ACCOUNT", "VIETQR_USER_BANK_NAME")
    return {
        "paypalClientId": paypal_client_id,
        "paypalCurrency": os.getenv("PAYPAL_CURRENCY", "USD").upper(),
        "paypalConfigured": bool(paypal_client_id and os.getenv("PAYPAL_CLIENT_SECRET", "").strip()),
        "vietqrConfigured": all(os.getenv(key, "").strip() for key in vietqr_keys),
    }


@app.get("/api/payments/orders/{order_id}/")
async def payment_for_order(order_id: str) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        row = await (await connection.execute("SELECT * FROM payment_service.payments WHERE order_id=%s", (order_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"transactionId": str(row["payment_id"]), "orderId": row["order_id"], "paymentMethod": row["provider"], "paymentStatus": row["status"], "paymentAmount": str(row["amount"]), "paymentCurrency": row["currency"], "captureId": row.get("capture_id")}


@app.post("/api/payments/orders/{order_id}/refund/")
async def refund_order(order_id: str, payload: OrderRefundRequest) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        row = await (await connection.execute("SELECT * FROM payment_service.payments WHERE order_id=%s", (order_id,))).fetchone()
    if not row or row["status"] not in {"SUCCESS", "COMPLETED"}:
        raise HTTPException(status_code=409, detail="A successful payment is required before refund")
    base = {"paymentMethod": row["provider"], "paymentStatus": row["status"], "paymentAmount": str(row["amount"]), "paymentCurrency": row["currency"], "captureId": row.get("capture_id"), "refundAmount": str(row["amount"]), "refundReason": payload.reason}
    if row["provider"] == "VIETQR":
        return {**base, "refundStatus": "MANUAL_REQUIRED", "refundMethod": "MANUAL_BANK_TRANSFER"}
    if row["provider"] != "PAYPAL" or not row.get("capture_id"):
        raise HTTPException(status_code=409, detail="The payment provider cannot refund this transaction")
    provider_payload = row.get("provider_payload") or {}
    capture_amount = provider_payload.get("paypalCapture", {}).get("amount", {})
    amount = Decimal(str(capture_amount.get("value", "0")))
    currency = capture_amount.get("currency_code", "USD")
    if amount <= 0:
        raise HTTPException(status_code=409, detail="PayPal capture amount is unavailable")
    token = await paypal_access_token()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{paypal_base_url()}/v2/payments/captures/{row['capture_id']}/refund",
            json={"amount": {"value": f"{amount:.2f}", "currency_code": currency}, "note_to_payer": payload.reason[:255]},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    data = response.json()
    if response.status_code != 201 or data.get("status") != "COMPLETED":
        raise HTTPException(status_code=502, detail=data.get("message", "PayPal refund failed"))
    async with await runtime.connect() as connection:
        await connection.execute("UPDATE payment_service.payments SET status='REFUNDED',provider_payload=provider_payload || %s,updated_at=now() WHERE order_id=%s", (Jsonb({"paypalRefund": data}), order_id))
    return {**base, "paymentStatus": "REFUNDED", "refundId": data["id"], "refundStatus": "SUCCESS", "refundMethod": "PAYPAL_API"}


@app.post("/api/payments/complete/", status_code=202)
async def complete_payment(payload: PaymentRequest) -> dict[str, Any]:
    row = await runtime.complete(payload)
    return {"paymentId": str(row["payment_id"]), "orderId": row["order_id"], "status": row["status"], "amount": str(row["amount"]), "currency": row["currency"], "provider": row["provider"]}


def vietqr_response(row: dict[str, Any]) -> dict[str, Any]:
    reference = f"AIMS-{str(row['payment_id']).split('-')[0].upper()}"
    provider_payload = row.get("provider_payload") or {}
    return {"transaction_id": str(row["payment_id"]), "order_id": row["order_id"], "payment_method": "VIETQR", "status": row["status"], "amount": str(row["amount"]), "currency": row["currency"], "transaction_reference": provider_payload.get("content", reference), "qr_payload": provider_payload.get("qrCode", ""), "qr_code": provider_payload.get("qrCode", ""), "qr_link": provider_payload.get("qrLink", ""), "qr_image_url": provider_payload.get("qrLink", "")}


@app.post("/api/payments/vietqr/qr-code/")
async def create_vietqr(payload: VietQRRequest) -> dict[str, Any]:
    # The browser-provided amount is only a display hint. The payment boundary
    # always charges the persisted server-side invoice to prevent tampering.
    invoice = await order_invoice(payload.order_id)
    payable_amount = Decimal(str(invoice["totalAmountToPay"]))
    row = await runtime.create_pending(payload.order_id, payable_amount)
    username = os.getenv("VIETQR_USERNAME", "").strip()
    password = os.getenv("VIETQR_PASSWORD", "").strip()
    base = os.getenv("VIETQR_BASE_URL", "https://dev.vietqr.org").rstrip("/")
    if not username or not password:
        raise HTTPException(status_code=503, detail="VietQR credentials are unavailable")
    reference = f"AIMS-{str(row['payment_id']).split('-')[0].upper()}"
    async with httpx.AsyncClient(timeout=float(os.getenv("VIETQR_REQUEST_TIMEOUT", "15"))) as client:
        token_response = await client.post(f"{base}/vqr/api/token_generate", auth=(username, password))
        if token_response.status_code != 200:
            raise HTTPException(status_code=502, detail="VietQR authentication failed")
        token = token_response.json().get("access_token")
        qr_response = await client.post(
            f"{base}/vqr/api/qr/generate-customer",
            json={
                "bankCode": os.getenv("VIETQR_BANK_CODE", ""),
                "bankAccount": os.getenv("VIETQR_BANK_ACCOUNT", ""),
                "userBankName": os.getenv("VIETQR_USER_BANK_NAME", ""),
                "content": reference,
                "qrType": 0,
                "amount": int(payable_amount),
                "orderId": reference,
                "transType": "C",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    try:
        provider_payload = qr_response.json()
    except ValueError:
        provider_payload = {}
    if qr_response.status_code >= 400 or provider_payload.get("status") == "FAILED" or not provider_payload.get("qrCode"):
        raise HTTPException(status_code=502, detail=provider_payload.get("message", "VietQR QR generation failed"))
    return vietqr_response(await runtime.update_provider_payload(row["payment_id"], provider_payload))


@app.post("/api/payments/paypal/initiate/", status_code=201)
async def initiate_paypal(payload: PayPalInitiateRequest) -> dict[str, Any]:
    invoice = await order_invoice(payload.order_id)
    source_amount_vnd = Decimal(str(invoice["totalAmountToPay"]))
    currency = payload.currency.upper()
    if currency != "USD":
        raise HTTPException(status_code=422, detail="PayPal payments are configured in USD")
    rate = Decimal(os.getenv("PAYPAL_VND_PER_USD", "25000"))
    paypal_amount = (source_amount_vnd / rate).quantize(Decimal("0.01"))
    if paypal_amount <= 0:
        paypal_amount = Decimal("0.01")
    token = await paypal_access_token()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{paypal_base_url()}/v2/checkout/orders",
            json={
                "intent": "CAPTURE",
                "purchase_units": [{"reference_id": payload.order_id, "description": payload.description or f"AIMS Order {payload.order_id}", "amount": {"currency_code": currency, "value": f"{paypal_amount:.2f}"}}],
                "application_context": {"return_url": payload.return_url, "cancel_url": payload.cancel_url, "brand_name": "AIMS Store", "landing_page": "LOGIN", "user_action": "PAY_NOW"},
            },
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    data = response.json()
    approval_url = next((link.get("href") for link in data.get("links", []) if link.get("rel") == "approve"), None)
    if response.status_code != 201 or not approval_url:
        raise HTTPException(status_code=502, detail=data.get("message", "PayPal order creation failed"))
    row = await runtime.save_provider_payment(order_id=payload.order_id, amount=source_amount_vnd, provider="PAYPAL", status="PENDING", provider_order_id=data["id"], provider_payload={"paypalAmount": f"{paypal_amount:.2f}", "paypalCurrency": currency})
    return {"provider_order_id": data["id"], "orderID": data["id"], "approval_url": approval_url, "transaction_id": str(row["payment_id"]), "amount": f"{paypal_amount:.2f}", "currency": currency, "source_amount_vnd": f"{source_amount_vnd:.2f}"}


@app.post("/api/payments/paypal/capture/")
async def capture_paypal(payload: PayPalCaptureRequest) -> dict[str, Any]:
    token = await paypal_access_token()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{paypal_base_url()}/v2/checkout/orders/{payload.provider_order_id}/capture", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    data = response.json()
    captures = data.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [])
    capture = captures[0] if captures else {}
    if response.status_code != 201 or data.get("status") != "COMPLETED" or not capture.get("id"):
        raise HTTPException(status_code=502, detail=data.get("message", "PayPal capture failed"))
    row = await runtime.finish_provider_payment(payload.provider_order_id, capture["id"], {"paypalCapture": capture})
    return {"transaction_id": str(row["payment_id"]), "order_id": row["order_id"], "gateway": "PAYPAL", "provider_order_id": payload.provider_order_id, "capture_id": capture["id"], "paypal_capture_id": capture["id"], "captured_amount": float(capture.get("amount", {}).get("value", 0)), "captured_currency": capture.get("amount", {}).get("currency_code", "USD"), "order_total_vnd": str(row["amount"]), "status": "SUCCESS"}


@app.post("/api/payments/paypal/refund/")
async def refund_paypal(payload: PayPalRefundRequest) -> dict[str, Any]:
    token = await paypal_access_token()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{paypal_base_url()}/v2/payments/captures/{payload.capture_id}/refund",
            json={"amount": {"value": f"{payload.amount:.2f}", "currency_code": payload.currency.upper()}, "note_to_payer": payload.reason[:255]},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    data = response.json()
    if response.status_code != 201 or data.get("status") != "COMPLETED":
        raise HTTPException(status_code=502, detail=data.get("message", "PayPal refund failed"))
    async with await runtime.connect() as connection:
        await connection.execute("UPDATE payment_service.payments SET status='REFUNDED',provider_payload=provider_payload || %s,updated_at=now() WHERE order_id=%s", (Jsonb({"paypalRefund": data}), payload.order_id))
    return {"refund_id": data["id"], "refunded_amount": float(data.get("amount", {}).get("value", payload.amount))}


@app.get("/api/payments/{transaction_id}/status/")
async def payment_status(transaction_id: uuid.UUID) -> dict[str, Any]:
    row = await runtime.get(transaction_id)
    if not row: raise HTTPException(status_code=404, detail="Payment not found")
    result = vietqr_response(row)
    return {key: result[key] for key in ("transaction_id", "order_id", "payment_method", "status", "amount", "currency", "transaction_reference")}


@app.post("/api/payments/vietqr/test-callback/")
async def test_callback(payload: CallbackRequest) -> dict[str, str]:
    if os.getenv("VIETQR_ENV", "dev").strip().lower() not in {"dev", "test", "sandbox"}:
        raise HTTPException(status_code=404, detail="Sandbox callback is disabled")
    row = await runtime.complete_by_id(payload.transaction_id)
    if not row: raise HTTPException(status_code=404, detail="Payment not found")
    return {"status": "SUCCESS", "message": "Sandbox payment completed"}
