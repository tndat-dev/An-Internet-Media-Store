"""OpenSearch adapter with a catalog fallback and owned interaction model."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS search_recommendation_service;
CREATE TABLE IF NOT EXISTS search_recommendation_service.interactions (
  id bigserial PRIMARY KEY, subject_id text NOT NULL, product_id text NOT NULL,
  action text NOT NULL, weight numeric(6,2) NOT NULL DEFAULT 1,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS recommendation_subject_time
  ON search_recommendation_service.interactions(subject_id, occurred_at DESC);
"""


class Interaction(BaseModel):
    subjectId: str = Field(min_length=1)
    productId: str = Field(min_length=1)
    action: str = Field(pattern="^(VIEW|CART|PURCHASE)$")


ACTION_WEIGHT = {"VIEW": 1, "CART": 3, "PURCHASE": 5}


class Runtime:
    def __init__(self) -> None:
        self.database_url = os.getenv("SEARCH_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
        self.ready = False

    async def start(self) -> None:
        if self.database_url:
            async with await psycopg.AsyncConnection.connect(self.database_url) as connection:
                await connection.execute("SELECT pg_advisory_xact_lock(hashtext('aims-search-schema-v1'))")
                await connection.execute(SCHEMA_SQL)
            self.ready = True

    async def connect(self) -> psycopg.AsyncConnection:
        if not self.database_url:
            raise HTTPException(status_code=503, detail="Recommendation database unavailable")
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)


runtime = Runtime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start(); yield


app = FastAPI(title="AIMS search-recommendation-service", version="1.0.0", lifespan=lifespan)


async def catalog_search(query: str, limit: int) -> list[dict[str, Any]]:
    url = os.getenv("CATALOG_SERVICE_URL", "http://catalog-service.production.svc.cluster.local:8000")
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(f"{url}/api/products/", params={"q": query, "page_size": limit})
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Catalog search unavailable")
    payload = response.json()
    return payload.get("results", payload if isinstance(payload, list) else [])


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "search-recommendation-service", "databaseReady": runtime.ready}


@app.get("/api/search/")
async def search(q: str = "", limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    return {"query": q, "results": await catalog_search(q, limit)}


@app.post("/api/recommendations/interactions", status_code=202)
async def record_interaction(payload: Interaction) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        await connection.execute("INSERT INTO search_recommendation_service.interactions(subject_id,product_id,action,weight) VALUES (%s,%s,%s,%s)", (payload.subjectId, payload.productId, payload.action, ACTION_WEIGHT[payload.action]))
    return {"accepted": True}


@app.get("/api/recommendations/{subject_id}")
async def recommend(subject_id: str, limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        cursor = await connection.execute("SELECT product_id,sum(weight) AS score FROM search_recommendation_service.interactions WHERE subject_id=%s GROUP BY product_id ORDER BY score DESC LIMIT %s", (subject_id, limit))
        rows = await cursor.fetchall()
    return {"subjectId": subject_id, "strategy": "weighted-interactions-v1", "products": [{"productId": row["product_id"], "score": float(row["score"])} for row in rows]}
