"""AIMS inventory boundary with idempotent Kafka consumption and outbox."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("aims.inventory")


class OrderItem(BaseModel):
    productId: str = Field(min_length=1)
    quantity: int = Field(ge=1)


class EventEnvelope(BaseModel):
    eventId: str = Field(min_length=1)
    eventType: str = Field(min_length=1)
    eventVersion: int = Field(ge=1)
    occurredAt: datetime
    aggregateId: str = Field(min_length=1)
    correlationId: str = Field(min_length=1)
    causationId: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def order_items(self) -> list[OrderItem]:
        return [OrderItem.model_validate(item) for item in self.payload.get("items", [])]


class StockAdjustment(BaseModel):
    delta: int


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS inventory_service;
CREATE TABLE IF NOT EXISTS inventory_service.stock (
  product_id text PRIMARY KEY,
  available integer NOT NULL CHECK (available >= 0),
  reserved integer NOT NULL DEFAULT 0 CHECK (reserved >= 0),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS inventory_service.processed_events (
  event_id text PRIMARY KEY,
  processed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS inventory_service.outbox_events (
  id bigserial PRIMARY KEY,
  topic text NOT NULL,
  message_key text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz
);
CREATE INDEX IF NOT EXISTS inventory_outbox_unpublished
  ON inventory_service.outbox_events (id) WHERE published_at IS NULL;
"""


class InventoryRuntime:
    def __init__(self) -> None:
        self.database_url = os.getenv("INVENTORY_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
        self.consumer: AIOKafkaConsumer | None = None
        self.producer: AIOKafkaProducer | None = None
        self.consumer_task: asyncio.Task[None] | None = None
        self.outbox_task: asyncio.Task[None] | None = None
        self.database_ready = False
        self.kafka_ready = False
        self.last_error: str | None = None

    @staticmethod
    def _ssl_context() -> ssl.SSLContext | None:
        cert = os.getenv("KAFKA_TLS_CERT", "/var/run/aims-kafka/user.crt")
        key = os.getenv("KAFKA_TLS_KEY", "/var/run/aims-kafka/user.key")
        ca = os.getenv("KAFKA_TLS_CA", "/var/run/aims-kafka-ca/ca.crt")
        if not all(os.path.exists(path) for path in (cert, key, ca)):
            return None
        context = ssl.create_default_context(cafile=ca)
        context.load_cert_chain(certfile=cert, keyfile=key)
        return context

    async def connect_database(self) -> None:
        if not self.database_url:
            logger.warning("Database disabled: INVENTORY_DATABASE_URL is not configured")
            return
        async with await psycopg.AsyncConnection.connect(self.database_url) as connection:
            await connection.execute(SCHEMA_SQL)
        self.database_ready = True

    async def start(self) -> None:
        await self.connect_database()
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        ssl_context = self._ssl_context()
        if not bootstrap or ssl_context is None:
            logger.warning("Kafka disabled: bootstrap or TLS material is unavailable")
            return
        common = {
            "bootstrap_servers": bootstrap,
            "security_protocol": "SSL",
            "ssl_context": ssl_context,
        }
        self.consumer = AIOKafkaConsumer(
            os.getenv("KAFKA_CONSUMER_TOPIC", "aims.business.order.created.v1"),
            group_id=os.getenv("KAFKA_CONSUMER_GROUP", "aims.inventory-service.v1"),
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            **common,
        )
        self.producer = AIOKafkaProducer(acks="all", enable_idempotence=True, **common)
        await self.producer.start()
        await self.consumer.start()
        self.kafka_ready = True
        self.consumer_task = asyncio.create_task(self._consume())
        self.outbox_task = asyncio.create_task(self._publish_outbox())

    async def stop(self) -> None:
        for task in (self.consumer_task, self.outbox_task):
            if task:
                task.cancel()
        await asyncio.gather(
            *(task for task in (self.consumer_task, self.outbox_task) if task),
            return_exceptions=True,
        )
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        self.kafka_ready = False

    async def _consume(self) -> None:
        assert self.consumer is not None
        try:
            async for message in self.consumer:
                event = EventEnvelope.model_validate(message.value)
                if event.eventType != "OrderCreated":
                    logger.info("Ignoring event type=%s eventId=%s", event.eventType, event.eventId)
                else:
                    await self.reserve_for_order(event)
                await self.consumer.commit()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.kafka_ready = False
            self.last_error = str(error)
            logger.exception("Inventory consumer stopped")

    async def reserve_for_order(self, event: EventEnvelope) -> bool:
        if not self.database_url:
            raise RuntimeError("Inventory database is unavailable")
        items = event.order_items()
        if not items:
            raise ValueError("OrderCreated payload.items must not be empty")

        async with await psycopg.AsyncConnection.connect(
            self.database_url, row_factory=dict_row
        ) as connection:
            async with connection.transaction():
                prior = await connection.execute(
                    "SELECT 1 FROM inventory_service.processed_events WHERE event_id=%s",
                    (event.eventId,),
                )
                if await prior.fetchone():
                    return True

                sufficient = True
                current: dict[str, int] = {}
                for item in sorted(items, key=lambda value: value.productId):
                    cursor = await connection.execute(
                        "SELECT available FROM inventory_service.stock "
                        "WHERE product_id=%s FOR UPDATE",
                        (item.productId,),
                    )
                    row = await cursor.fetchone()
                    current[item.productId] = int(row["available"]) if row else 0
                    sufficient = sufficient and current[item.productId] >= item.quantity

                if sufficient:
                    for item in items:
                        await connection.execute(
                            "UPDATE inventory_service.stock "
                            "SET available=available-%s, reserved=reserved+%s, updated_at=now() "
                            "WHERE product_id=%s",
                            (item.quantity, item.quantity, item.productId),
                        )

                event_type = "InventoryReserved" if sufficient else "InventoryRejected"
                topic = os.getenv(
                    "KAFKA_OUTPUT_TOPIC_SUCCESS" if sufficient else "KAFKA_OUTPUT_TOPIC_FAILURE",
                    "aims.business.inventory.reserved.v1"
                    if sufficient
                    else "aims.business.inventory.rejected.v1",
                )
                outgoing = {
                    "eventId": str(uuid.uuid4()),
                    "eventType": event_type,
                    "eventVersion": 1,
                    "occurredAt": datetime.now(timezone.utc).isoformat(),
                    "aggregateId": event.aggregateId,
                    "correlationId": event.correlationId,
                    "causationId": event.eventId,
                    "payload": {
                        "reservationId": str(uuid.uuid4()),
                        "status": "RESERVED" if sufficient else "REJECTED",
                        "items": [item.model_dump() for item in items],
                    },
                }
                await connection.execute(
                    "INSERT INTO inventory_service.outbox_events(topic,message_key,payload) "
                    "VALUES (%s,%s,%s)",
                    (topic, event.aggregateId, Jsonb(outgoing)),
                )
                await connection.execute(
                    "INSERT INTO inventory_service.processed_events(event_id) VALUES (%s)",
                    (event.eventId,),
                )
        return sufficient

    async def _publish_outbox(self) -> None:
        assert self.producer is not None
        while True:
            try:
                if not self.database_url:
                    await asyncio.sleep(2)
                    continue
                async with await psycopg.AsyncConnection.connect(
                    self.database_url, row_factory=dict_row
                ) as connection:
                    cursor = await connection.execute(
                        "SELECT id,topic,message_key,payload "
                        "FROM inventory_service.outbox_events "
                        "WHERE published_at IS NULL ORDER BY id LIMIT 1"
                    )
                    record = await cursor.fetchone()
                    if not record:
                        await asyncio.sleep(1)
                        continue
                    await self.producer.send_and_wait(
                        record["topic"],
                        json.dumps(record["payload"]).encode("utf-8"),
                        key=record["message_key"].encode("utf-8"),
                    )
                    await connection.execute(
                        "UPDATE inventory_service.outbox_events SET published_at=now() WHERE id=%s",
                        (record["id"],),
                    )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.last_error = str(error)
                logger.exception("Outbox publish failed; retrying")
                await asyncio.sleep(3)

    async def adjust(self, product_id: str, delta: int) -> dict[str, Any]:
        if not self.database_url:
            raise RuntimeError("Inventory database is unavailable")
        async with await psycopg.AsyncConnection.connect(
            self.database_url, row_factory=dict_row
        ) as connection:
            cursor = await connection.execute(
                "INSERT INTO inventory_service.stock(product_id,available) VALUES (%s,%s) "
                "ON CONFLICT(product_id) DO UPDATE "
                "SET available=inventory_service.stock.available+EXCLUDED.available, updated_at=now() "
                "WHERE inventory_service.stock.available+EXCLUDED.available >= 0 "
                "RETURNING product_id,available,reserved,updated_at",
                (product_id, delta),
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError("Adjustment would make available stock negative")
            return dict(row)

    async def stock(self, product_id: str) -> dict[str, Any] | None:
        if not self.database_url:
            raise RuntimeError("Inventory database is unavailable")
        async with await psycopg.AsyncConnection.connect(
            self.database_url, row_factory=dict_row
        ) as connection:
            cursor = await connection.execute(
                "SELECT product_id,available,reserved,updated_at "
                "FROM inventory_service.stock WHERE product_id=%s",
                (product_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None


runtime = InventoryRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await runtime.start()
    except Exception as error:
        runtime.last_error = str(error)
        logger.exception("Inventory runtime initialization failed")
    yield
    await runtime.stop()


app = FastAPI(title="AIMS inventory-service", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "inventory-service"}


@app.get("/readyz")
async def readiness() -> dict[str, Any]:
    return {
        "status": "ok" if runtime.database_ready and runtime.kafka_ready else "degraded",
        "databaseReady": runtime.database_ready,
        "kafkaReady": runtime.kafka_ready,
        "lastError": runtime.last_error,
    }


@app.post("/api/inventory/{product_id}/adjust")
async def adjust_stock(product_id: str, adjustment: StockAdjustment) -> dict[str, Any]:
    try:
        return await runtime.adjust(product_id, adjustment.delta)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/inventory/{product_id}")
async def get_stock(product_id: str) -> dict[str, Any]:
    try:
        result = await runtime.stock(product_id)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="Product stock not found")
    return result
