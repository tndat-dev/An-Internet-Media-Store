"""Product catalog with schema ownership and no Django imports."""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS catalog_service;
CREATE TABLE IF NOT EXISTS catalog_service.products (
  product_id uuid PRIMARY KEY,
  title text NOT NULL,
  product_type text NOT NULL,
  category text NOT NULL DEFAULT '',
  price numeric(14,2) NOT NULL CHECK(price >= 0),
  original_value numeric(14,2) NOT NULL DEFAULT 0,
  height numeric(10,2) NOT NULL DEFAULT 0,
  width numeric(10,2) NOT NULL DEFAULT 0,
  length numeric(10,2) NOT NULL DEFAULT 0,
  weight numeric(10,2) NOT NULL DEFAULT 0,
  barcode text UNIQUE,
  stock_quantity integer NOT NULL DEFAULT 0,
  description text NOT NULL DEFAULT '',
  image_url text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'ACTIVE',
  type_details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS catalog_product_search
  ON catalog_service.products USING gin(to_tsvector('simple', title || ' ' || description));
DO $$
BEGIN
  IF to_regclass('public.products_product') IS NOT NULL THEN
    INSERT INTO catalog_service.products(
      product_id,title,product_type,category,price,original_value,height,width,length,
      weight,barcode,stock_quantity,description,image_url,status,created_at,updated_at
    )
    SELECT product_id,title,product_type,category,current_price,original_value,height,
      width,length,weight,barcode,stock_quantity,general_description,image_url,status,
      created_at,updated_at
    FROM public.products_product
    ON CONFLICT(product_id) DO NOTHING;
  END IF;
END $$;
"""


class ProductInput(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    product_type: str = Field(default="BOOK", min_length=1)
    category: str = ""
    current_price: Decimal = Field(ge=0)
    original_value: Decimal = Field(ge=0)
    height: Decimal = Field(default=Decimal("0"), ge=0)
    width: Decimal = Field(default=Decimal("0"), ge=0)
    length: Decimal = Field(default=Decimal("0"), ge=0)
    weight: Decimal = Field(default=Decimal("0"), ge=0)
    barcode: str | None = None
    stock_quantity: int = Field(default=0, ge=0)
    general_description: str = ""
    image_url: str = ""
    status: str = "ACTIVE"
    type_details: dict[str, Any] = Field(default_factory=dict)


class CatalogRuntime:
    def __init__(self) -> None:
        self.database_url = os.getenv("CATALOG_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
        self.ready = False
        self.last_error: str | None = None

    async def start(self) -> None:
        if not self.database_url:
            return
        async with await psycopg.AsyncConnection.connect(self.database_url) as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext('aims-catalog-schema-v1'))")
            await connection.execute(SCHEMA_SQL)
        self.ready = True

    async def connect(self) -> psycopg.AsyncConnection:
        if not self.database_url:
            raise HTTPException(status_code=503, detail="Catalog database unavailable")
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)


runtime = CatalogRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await runtime.start()
    except Exception as error:
        runtime.last_error = str(error)
    yield


app = FastAPI(title="AIMS catalog-service", version="1.0.0", lifespan=lifespan)


def encode_product(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["product_id"] = str(result["product_id"])
    for key in ("price", "original_value", "height", "width", "length", "weight"):
        result[key] = str(result[key])
    result["current_price"] = result["price"]
    result["description"] = result.get("description", "")
    result["general_description"] = result["description"]
    result["type_details"] = result.get("type_details", {})
    result["is_available"] = result["status"] == "ACTIVE" and result["stock_quantity"] > 0
    return result


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "catalog-service", "databaseReady": runtime.ready}


@app.get("/api/products/")
async def list_products(q: str = "", search: str = "", page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        pattern = f"%{search or q}%"
        total_cursor = await connection.execute(
            "SELECT count(*) AS count FROM catalog_service.products WHERE status='ACTIVE' AND (title ILIKE %s OR description ILIKE %s)",
            (pattern, pattern),
        )
        total = (await total_cursor.fetchone())["count"]
        cursor = await connection.execute(
            "SELECT * FROM catalog_service.products WHERE status='ACTIVE' AND (title ILIKE %s OR description ILIKE %s) ORDER BY updated_at DESC LIMIT %s OFFSET %s",
            (pattern, pattern, page_size, (page - 1) * page_size),
        )
        rows = await cursor.fetchall()
    return {"count": total, "next": None, "previous": None, "results": [encode_product(row) for row in rows]}


@app.post("/api/products/", status_code=201)
async def create_product(payload: ProductInput) -> dict[str, Any]:
    product_id = uuid.uuid4()
    async with await runtime.connect() as connection:
        cursor = await connection.execute(
            "INSERT INTO catalog_service.products(product_id,title,product_type,category,price,original_value,height,width,length,weight,barcode,stock_quantity,description,image_url,status,type_details) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (product_id, payload.title, payload.product_type, payload.category, payload.current_price, payload.original_value, payload.height, payload.width, payload.length, payload.weight, payload.barcode, payload.stock_quantity, payload.general_description, payload.image_url, payload.status, Jsonb(payload.type_details)),
        )
        row = await cursor.fetchone()
    return encode_product(row)


@app.get("/api/products/{product_id}/")
async def get_product(product_id: uuid.UUID) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        cursor = await connection.execute("SELECT * FROM catalog_service.products WHERE product_id=%s AND status!='DELETED'", (product_id,))
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return encode_product(row)
