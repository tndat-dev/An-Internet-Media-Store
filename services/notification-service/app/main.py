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

from app.observability import install_observability

import aio_pika
from aiokafka import AIOKafkaConsumer
from aiokafka.structs import TopicPartition
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
        self.tasks: list[asyncio.Task] = []
        self.rabbit_connection: Any = None
        self.rabbit_channel: Any = None
        self.task_exchange: Any = None
        self.notification_queue: Any = None
        self.running = False
        self.rabbit_ready = False
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
        await self.start_rabbit()
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        if not bootstrap:
            logger.info("Kafka disabled: KAFKA_BOOTSTRAP_SERVERS is not configured")
            return
        ssl_context = self._ssl_context()
        if ssl_context is None:
            self.last_error = "Kafka TLS files are unavailable"
            logger.warning(self.last_error)
            return
        topics = list(dict.fromkeys([
            os.getenv("KAFKA_CONSUMER_TOPIC", os.getenv("KAFKA_NOTIFICATION_TOPIC", "aims.business.payment.completed.v1")),
            os.getenv("KAFKA_LIFECYCLE_TOPIC", "aims.business.order.lifecycle.v1"),
        ]))
        self.consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap,
            group_id=os.getenv("KAFKA_CONSUMER_GROUP", "aims-notification-service.v1"),
            security_protocol="SSL",
            ssl_context=ssl_context,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        self.running = True
        self.tasks.append(asyncio.create_task(self._consume_forever()))

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
            client_properties={"connection_name": "aims-notification-service"},
        )
        self.rabbit_channel = await self.rabbit_connection.channel()
        await self.rabbit_channel.set_qos(prefetch_count=20)
        # The Topology Operator owns declarations; application identities are
        # deliberately unable to configure broker objects.
        self.task_exchange = await self.rabbit_channel.get_exchange("aims.tasks", ensure=False)
        self.notification_queue = await self.rabbit_channel.get_queue("notification.tasks", ensure=False)
        self.rabbit_ready = True
        self.tasks.append(asyncio.create_task(self._consume_notification_tasks()))

    async def stop(self) -> None:
        self.running = False
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.consumer:
            await self.consumer.stop()
        if self.rabbit_connection:
            await self.rabbit_connection.close()
        self.rabbit_ready = False

    async def _consume_forever(self) -> None:
        assert self.consumer is not None
        try:
            await self.consumer.start()
            async for message in self.consumer:
                event = EventEnvelope.model_validate(message.value)
                try:
                    await self.publish_task(event)
                except Exception as error:
                    self.last_error = str(error)
                    self.rabbit_ready = False
                    self.consumer.seek(
                        TopicPartition(message.topic, message.partition), message.offset
                    )
                    await asyncio.sleep(3)
                    continue
                await self.consumer.commit()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # readiness must not flap during broker recovery
            self.last_error = str(error)
            logger.exception("Kafka consumer stopped; Kubernetes will restart the pod")
            self.running = False

    async def publish_task(self, event: EventEnvelope) -> None:
        if event.eventType not in {"PaymentCompleted", "OrderConfirmed", "OrderApproved", "OrderRejected", "OrderCancelled"}:
            return
        if not self.task_exchange:
            raise RuntimeError("RabbitMQ task exchange is unavailable")
        await self.task_exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json().encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
                message_id=event.eventId,
                correlation_id=event.correlationId,
            ),
            routing_key="notification.deliver",
        )
        self.rabbit_ready = True

    async def _consume_notification_tasks(self) -> None:
        assert self.notification_queue is not None
        async with self.notification_queue.iterator() as iterator:
            async for message in iterator:
                try:
                    async with message.process(requeue=False):
                        event = EventEnvelope.model_validate_json(message.body)
                        await self.deliver(event)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Notification task rejected to DLQ")

    async def deliver(self, event: EventEnvelope) -> None:
        """Delivery adapter seam. Logging is safe for the first extracted slice."""
        if event.eventType not in {"PaymentCompleted", "OrderConfirmed", "OrderApproved", "OrderRejected", "OrderCancelled"}:
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
install_observability(app)


@app.get("/healthz")
@app.get("/api/health/")
@app.get("/api/notifications/healthz")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "notification-service", "kafkaReady": runtime.running, "rabbitReady": runtime.rabbit_ready, "processed": runtime.processed, "lastError": runtime.last_error}


@app.get("/readyz")
async def readiness() -> dict[str, Any]:
    # A broker outage is observable but does not make the HTTP process unhealthy.
    return {"status": "ok", "kafkaConsumerRunning": runtime.running, "rabbitConsumerRunning": runtime.rabbit_ready, "lastError": runtime.last_error}


@app.post("/api/notifications/events", status_code=202)
async def accept_internal_event(event: EventEnvelope) -> dict[str, Any]:
    if event.eventType not in {"PaymentCompleted", "OrderConfirmed", "OrderApproved", "OrderRejected", "OrderCancelled"}:
        raise HTTPException(status_code=422, detail="Unsupported eventType")
    if not runtime.rabbit_ready:
        raise HTTPException(status_code=503, detail="RabbitMQ task queue unavailable")
    await runtime.publish_task(event)
    return {"accepted": True, "eventId": event.eventId}
