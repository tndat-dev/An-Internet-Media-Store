"""Kafka-driven notification boundary for the AIMS strangler migration.

The service deliberately has no import from Programming/backend. It consumes
versioned business events using its own consumer group and exposes only health
and an internal test/delivery endpoint. Delivery is currently logged; SMTP,
webhook and durable inbox adapters can be added without coupling to Order or
Payment models.
"""

import asyncio
import json
import logging
import os
import ssl
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from aiokafka import AIOKafkaConsumer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("aims.notification")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


class EventEnvelope(BaseModel):
    eventId: str = Field(min_length=1)
    eventType: str = Field(min_length=1)
    eventVersion: int = Field(ge=1)
    occurredAt: datetime
    aggregateId: str = Field(min_length=1)
    correlationId: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class NotificationRuntime:
    """Owns Kafka lifecycle; readiness stays true when Kafka reconnects."""

    def __init__(self) -> None:
        self.consumer: AIOKafkaConsumer | None = None
        self.task: asyncio.Task[None] | None = None
        self.running = False
        self.processed = 0
        self.last_error: str | None = None

    @staticmethod
    def _ssl_context() -> ssl.SSLContext | None:
        cert = os.getenv("KAFKA_TLS_CERT", "/var/run/aims-kafka/user.crt")
        key = os.getenv("KAFKA_TLS_KEY", "/var/run/aims-kafka/user.key")
        ca = os.getenv("KAFKA_TLS_CA", "/var/run/aims-kafka/ca.crt")
        if not all(os.path.exists(path) for path in (cert, key, ca)):
            return None
        context = ssl.create_default_context(cafile=ca)
        context.load_cert_chain(certfile=cert, keyfile=key)
        return context

    async def start(self) -> None:
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        if not bootstrap:
            logger.info("Kafka disabled: KAFKA_BOOTSTRAP_SERVERS is not configured")
            return
        ssl_context = self._ssl_context()
        if ssl_context is None:
            self.last_error = "Kafka TLS files are unavailable"
            logger.warning(self.last_error)
            return
        self.consumer = AIOKafkaConsumer(
            os.getenv("KAFKA_NOTIFICATION_TOPIC", "aims.business.payment.completed.v1"),
            bootstrap_servers=bootstrap,
            group_id=os.getenv("KAFKA_CONSUMER_GROUP", "aims-notification-service.v1"),
            security_protocol="SSL",
            ssl_context=ssl_context,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        self.running = True
        self.task = asyncio.create_task(self._consume_forever())

    async def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.consumer:
            await self.consumer.stop()

    async def _consume_forever(self) -> None:
        assert self.consumer is not None
        try:
            await self.consumer.start()
            async for message in self.consumer:
                event = EventEnvelope.model_validate(message.value)
                await self.deliver(event)
                await self.consumer.commit()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # readiness must not flap during broker recovery
            self.last_error = str(error)
            logger.exception("Kafka consumer stopped; Kubernetes will restart the pod")
            self.running = False

    async def deliver(self, event: EventEnvelope) -> None:
        """Delivery adapter seam. Logging is safe for the first extracted slice."""
        if event.eventType not in {"PaymentCompleted", "OrderConfirmed"}:
            logger.info("Ignoring event type=%s eventId=%s", event.eventType, event.eventId)
            return
        self.processed += 1
        logger.info(
            "notification-delivered eventId=%s aggregateId=%s correlationId=%s at=%s",
            event.eventId,
            event.aggregateId,
            event.correlationId,
            datetime.now(timezone.utc).isoformat(),
        )


runtime = NotificationRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="AIMS notification-service", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "notification-service"}


@app.get("/readyz")
async def readiness() -> dict[str, Any]:
    # A broker outage is observable but does not make the HTTP process unhealthy.
    return {"status": "ok", "kafkaConsumerRunning": runtime.running, "lastError": runtime.last_error}


@app.post("/api/notifications/events", status_code=202)
async def accept_internal_event(event: EventEnvelope) -> dict[str, Any]:
    if event.eventType not in {"PaymentCompleted", "OrderConfirmed"}:
        raise HTTPException(status_code=422, detail="Unsupported eventType")
    await runtime.deliver(event)
    return {"accepted": True, "eventId": event.eventId}
