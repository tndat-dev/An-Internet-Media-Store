"""Kafka audit consumer with an online Isolation Forest scoring window."""

from __future__ import annotations

import asyncio
import json
import os
import ssl
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg
from aiokafka import AIOKafkaConsumer
from fastapi import FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field
from sklearn.ensemble import IsolationForest

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS security_telemetry_service;
CREATE TABLE IF NOT EXISTS security_telemetry_service.events (
  id bigserial PRIMARY KEY, source text NOT NULL, event_type text NOT NULL,
  severity integer NOT NULL, feature_vector jsonb NOT NULL, payload jsonb NOT NULL,
  anomaly boolean NOT NULL, anomaly_score double precision,
  occurred_at timestamptz NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS security_anomaly_time ON security_telemetry_service.events(anomaly, occurred_at DESC);
"""


class TelemetryEvent(BaseModel):
    source: str = Field(min_length=1)
    eventType: str = Field(min_length=1)
    severity: int = Field(default=1, ge=0, le=10)
    syscallRate: float = 0
    networkRate: float = 0
    deniedCount: float = 0
    occurredAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)

    def features(self) -> list[float]:
        return [float(self.severity), self.syscallRate, self.networkRate, self.deniedCount]


class Detector:
    def __init__(self, max_samples: int = 512) -> None:
        self.samples: deque[list[float]] = deque(maxlen=max_samples)

    def score(self, features: list[float]) -> tuple[bool, float | None]:
        self.samples.append(features)
        if len(self.samples) < 32:
            return False, None
        model = IsolationForest(n_estimators=64, contamination=0.05, random_state=42, n_jobs=1)
        model.fit(list(self.samples))
        score = float(model.decision_function([features])[0])
        return score < 0, score


def kafka_tls() -> ssl.SSLContext | None:
    cert, key, ca = (os.getenv("KAFKA_TLS_CERT", "/var/run/aims-kafka/user.crt"), os.getenv("KAFKA_TLS_KEY", "/var/run/aims-kafka/user.key"), os.getenv("KAFKA_TLS_CA", "/var/run/aims-kafka-ca/ca.crt"))
    if not all(os.path.exists(path) for path in (cert, key, ca)): return None
    context = ssl.create_default_context(cafile=ca); context.load_cert_chain(cert, key); return context


class Runtime:
    def __init__(self) -> None:
        self.database_url = os.getenv("SECURITY_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
        self.detector = Detector()
        self.consumer: AIOKafkaConsumer | None = None
        self.task: asyncio.Task | None = None
        self.database_ready = False
        self.kafka_ready = False

    async def connect(self) -> psycopg.AsyncConnection:
        if not self.database_url: raise HTTPException(status_code=503, detail="Security database unavailable")
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)

    async def start(self) -> None:
        if self.database_url:
            async with await psycopg.AsyncConnection.connect(self.database_url) as connection:
                await connection.execute("SELECT pg_advisory_xact_lock(hashtext('aims-security-schema-v1'))")
                await connection.execute(SCHEMA_SQL)
            self.database_ready = True
        bootstrap, tls = os.getenv("KAFKA_BOOTSTRAP_SERVERS", ""), kafka_tls()
        if bootstrap and tls:
            self.consumer = AIOKafkaConsumer(os.getenv("KAFKA_CONSUMER_TOPIC", os.getenv("KAFKA_SECURITY_TOPIC", "aims-security-events")), bootstrap_servers=bootstrap, group_id="aims.security-telemetry-service.v1", security_protocol="SSL", ssl_context=tls, enable_auto_commit=False, value_deserializer=lambda value: json.loads(value.decode()))
            await self.consumer.start(); self.kafka_ready = True; self.task = asyncio.create_task(self.consume())

    async def stop(self) -> None:
        if self.task: self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True)
        if self.consumer: await self.consumer.stop()

    async def consume(self) -> None:
        assert self.consumer
        async for message in self.consumer:
            raw = message.value
            event = TelemetryEvent(source=raw.get("source", "kafka"), eventType=raw.get("eventType", raw.get("type", "unknown")), severity=int(raw.get("severity", 1)), syscallRate=float(raw.get("syscallRate", 0)), networkRate=float(raw.get("networkRate", 0)), deniedCount=float(raw.get("deniedCount", 0)), occurredAt=raw.get("occurredAt", datetime.now(timezone.utc)), payload=raw)
            await self.ingest(event); await self.consumer.commit()

    async def ingest(self, event: TelemetryEvent) -> dict[str, Any]:
        anomaly, score = self.detector.score(event.features())
        async with await self.connect() as connection:
            cursor = await connection.execute("INSERT INTO security_telemetry_service.events(source,event_type,severity,feature_vector,payload,anomaly,anomaly_score,occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id", (event.source, event.eventType, event.severity, Jsonb(event.features()), Jsonb(event.payload), anomaly, score, event.occurredAt))
            event_id = (await cursor.fetchone())["id"]
        return {"id": event_id, "anomaly": anomaly, "score": score, "detector": "IsolationForest-v1"}


runtime = Runtime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try: await runtime.start()
    except Exception: pass
    yield
    await runtime.stop()


app = FastAPI(title="AIMS security-telemetry-service", version="1.0.0", lifespan=lifespan)


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, Any]: return {"status": "ok", "service": "security-telemetry-service", "databaseReady": runtime.database_ready, "kafkaReady": runtime.kafka_ready, "model": "IsolationForest"}


@app.post("/api/security/events", status_code=202)
async def ingest(event: TelemetryEvent) -> dict[str, Any]: return await runtime.ingest(event)


@app.get("/api/security/anomalies")
async def anomalies(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
    async with await runtime.connect() as connection:
        cursor = await connection.execute("SELECT id,source,event_type,severity,anomaly_score,occurred_at FROM security_telemetry_service.events WHERE anomaly ORDER BY occurred_at DESC LIMIT %s", (limit,)); rows = await cursor.fetchall()
    return [dict(row) for row in rows]
