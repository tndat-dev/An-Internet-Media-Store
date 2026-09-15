"""Product catalog with schema ownership and no Django imports."""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import httpx
import psycopg
from fastapi import FastAPI, Header, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.observability import install_observability

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
CREATE TABLE IF NOT EXISTS catalog_service.product_history (
  history_id uuid PRIMARY KEY, product_id uuid NOT NULL, product_title text NOT NULL,
  action_type text NOT NULL, performed_by text, reason text NOT NULL DEFAULT '',
  changes jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS catalog_history_product_created
  ON catalog_service.product_history(product_id, created_at DESC);
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


class DeleteProductsInput(BaseModel):
    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


REQUIRED_TYPE_FIELDS = {
    "BOOK": {"authors", "cover_type", "publisher", "publication_date"},
    "NEWSPAPER": {"editor_in_chief", "publisher", "publication_date"},
    "CD": {"artists", "record_label", "tracklist", "genre"},
    "DVD": {"disc_type", "director", "runtime_minutes", "studio", "language", "subtitles"},
}


def validate_product(payload: ProductInput) -> None:
    if payload.original_value <= 0:
        raise HTTPException(status_code=422, detail={"original_value": "Original value must be greater than zero"})
    lower, upper = payload.original_value * Decimal("0.30"), payload.original_value * Decimal("1.50")
    if not lower <= payload.current_price <= upper:
        raise HTTPException(status_code=422, detail={"current_price": "Current price must be between 30% and 150% of original value"})
    product_type = payload.product_type.upper()
    if product_type not in REQUIRED_TYPE_FIELDS:
        raise HTTPException(status_code=422, detail={"product_type": "Supported types are BOOK, NEWSPAPER, CD and DVD"})
    missing = sorted(key for key in REQUIRED_TYPE_FIELDS[product_type] if payload.type_details.get(key) in (None, ""))
    if missing:
        raise HTTPException(status_code=422, detail={"type_details": f"Missing required fields: {', '.join(missing)}"})


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


async def adjust_inventory(product_id: uuid.UUID, delta: int, reason: str, authorization: str) -> None:
    if delta == 0:
        return
    inventory_url = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service.production.svc.cluster.local:8000").rstrip("/")
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.post(
            f"{inventory_url}/api/inventory/{product_id}/adjust",
            json={"delta": delta, "reason": reason},
            headers={"Authorization": authorization},
        )
    if response.status_code != 200:
        detail = response.json().get("detail", "Inventory adjustment failed") if response.headers.get("content-type", "").startswith("application/json") else "Inventory adjustment failed"
        raise HTTPException(status_code=response.status_code, detail=detail)


def snapshot_product(row: dict[str, Any]) -> dict[str, Any]:
    value = encode_product(row)
    return {key: value.get(key) for key in ("product_id", "title", "product_type", "category", "current_price", "original_value", "stock_quantity", "status", "type_details")}


async def add_history(connection: psycopg.AsyncConnection, row: dict[str, Any], action: str, performer: str, *, before: dict[str, Any] | None = None, reason: str = "") -> None:
    await connection.execute(
        "INSERT INTO catalog_service.product_history(history_id,product_id,product_title,action_type,performed_by,reason,changes) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (uuid.uuid4(), row["product_id"], row["title"], action, performer, reason, Jsonb({"before": before, "after": None if action == "DELETE" else snapshot_product(row)})),
    )


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
install_observability(app)


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
async def list_products(
    q: str = "", search: str = "", category: str = "", scope: str = "",
    min_price: Decimal | None = Query(default=None, ge=0), max_price: Decimal | None = Query(default=None, ge=0),
    sort: str = "", page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    authorization: str | None = Header(default=None),
) -> Any:
    if scope == "manager":
        await require_product_manager(authorization)
    term = search or q
    clauses = ["status!='DELETED'" if scope == "manager" else "status='ACTIVE'", "(title ILIKE %s OR category ILIKE %s OR description ILIKE %s)"]
    params: list[Any] = [f"%{term}%", f"%{term}%", f"%{term}%"]
    if category:
        clauses.append("category=%s"); params.append(category)
    if min_price is not None:
        clauses.append("price >= %s"); params.append(min_price)
    if max_price is not None:
        clauses.append("price <= %s"); params.append(max_price)
    where = " AND ".join(clauses)
    order_by = {"title": "title ASC", "newest": "created_at DESC", "price_asc": "price ASC", "price_desc": "price DESC"}.get(sort, "updated_at DESC")
    if scope == "customer" and page == 1 and not any((term, category, min_price is not None, max_price is not None, sort)):
        order_by = "random()"
    async with await runtime.connect() as connection:
        total_cursor = await connection.execute(
            f"SELECT count(*) AS count FROM catalog_service.products WHERE {where}", params,
        )
        total = (await total_cursor.fetchone())["count"]
        cursor = await connection.execute(
            f"SELECT * FROM catalog_service.products WHERE {where} ORDER BY {order_by} LIMIT %s OFFSET %s",
            [*params, page_size, (page - 1) * page_size],
        )
        rows = await cursor.fetchall()
    rendered = [encode_product(row) for row in rows]
    if scope == "manager":
        return rendered
    return {"count": total, "next": page + 1 if page * page_size < total else None, "previous": page - 1 if page > 1 else None, "results": rendered}


@app.post("/api/products/", status_code=201)
async def create_product(payload: ProductInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = await require_product_manager(authorization)
    validate_product(payload)
    product_id = uuid.uuid4()
    async with await runtime.connect() as connection:
        cursor = await connection.execute(
            "INSERT INTO catalog_service.products(product_id,title,product_type,category,price,original_value,height,width,length,weight,barcode,stock_quantity,description,image_url,status,type_details) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (product_id, payload.title, payload.product_type, payload.category, payload.current_price, payload.original_value, payload.height, payload.width, payload.length, payload.weight, payload.barcode, payload.stock_quantity, payload.general_description, payload.image_url, payload.status, Jsonb(payload.type_details)),
        )
        row = await cursor.fetchone()
        await add_history(connection, row, "CREATE", user["username"])
        if payload.stock_quantity:
            await adjust_inventory(product_id, payload.stock_quantity, "Initial product stock", authorization or "")
    return encode_product(row)


@app.patch("/api/products/{product_id}/")
async def update_product(product_id: uuid.UUID, changes: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = await require_product_manager(authorization)
    async with await runtime.connect() as connection:
        cursor = await connection.execute("SELECT * FROM catalog_service.products WHERE product_id=%s AND status!='DELETED'", (product_id,))
        current = await cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Product not found")
        before = snapshot_product(current)
        merged = {**encode_product(current), **changes}
        merged["general_description"] = merged.get("general_description", merged.get("description", ""))
        payload = ProductInput.model_validate(merged)
        validate_product(payload)
        stock_delta = payload.stock_quantity - int(current["stock_quantity"])
        reason = str(changes.get("stock_adjustment_reason", "")).strip()
        if stock_delta and not reason:
            raise HTTPException(status_code=422, detail={"stock_adjustment_reason": "A reason is required when stock changes"})
        if stock_delta:
            await adjust_inventory(product_id, stock_delta, reason, authorization or "")
        cursor = await connection.execute(
            "UPDATE catalog_service.products SET title=%s,product_type=%s,category=%s,price=%s,original_value=%s,height=%s,width=%s,length=%s,weight=%s,barcode=%s,stock_quantity=%s,description=%s,image_url=%s,status=%s,type_details=%s,updated_at=now() WHERE product_id=%s RETURNING *",
            (payload.title, payload.product_type, payload.category, payload.current_price, payload.original_value, payload.height, payload.width, payload.length, payload.weight, payload.barcode, payload.stock_quantity, payload.general_description, payload.image_url, payload.status, Jsonb(payload.type_details), product_id),
        )
        row = await cursor.fetchone()
        await add_history(connection, row, "STOCK_ADJUST" if stock_delta else "UPDATE", user["username"], before=before, reason=reason)
    return encode_product(row)


@app.post("/api/products/delete/")
async def delete_products(payload: DeleteProductsInput, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    user = await require_product_manager(authorization)
    results = []
    async with await runtime.connect() as connection:
        used_cursor = await connection.execute("SELECT count(*) AS count FROM catalog_service.product_history WHERE performed_by=%s AND action_type IN ('DELETE','DEACTIVATE') AND created_at >= current_date", (user["username"],))
        used = (await used_cursor.fetchone())["count"]
        if used + len(payload.product_ids) > 20:
            raise HTTPException(status_code=429, detail="A manager cannot delete more than 20 products per day")
        for product_id in payload.product_ids:
            cursor = await connection.execute("SELECT * FROM catalog_service.products WHERE product_id=%s AND status!='DELETED'", (product_id,))
            current = await cursor.fetchone()
            if not current:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
            before = snapshot_product(current)
            action, status = ("DELETE", "DELETED") if current["stock_quantity"] == 0 else ("DEACTIVATE", "DEACTIVATED")
            cursor = await connection.execute("UPDATE catalog_service.products SET status=%s,updated_at=now() WHERE product_id=%s RETURNING *", (status, product_id))
            row = await cursor.fetchone()
            await add_history(connection, row, action, user["username"], before=before, reason="Bulk delete request")
            results.append(encode_product(row))
    return results


@app.get("/api/products/histories/")
async def product_history(product_id: uuid.UUID | None = None, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    await require_product_manager(authorization)
    query = "SELECT * FROM catalog_service.product_history"
    params: tuple[Any, ...] = ()
    if product_id:
        query += " WHERE product_id=%s"; params = (product_id,)
    query += " ORDER BY created_at DESC LIMIT 500"
    async with await runtime.connect() as connection:
        rows = await (await connection.execute(query, params)).fetchall()
    return [{"history_id": str(row["history_id"]), "product_id": str(row["product_id"]), "product_title": row["product_title"], "action_type": row["action_type"], "performed_by": row["performed_by"], "reason": row["reason"], "changes": row["changes"], "created_at": row["created_at"].isoformat()} for row in rows]


@app.get("/api/products/{product_id}/")
async def get_product(product_id: uuid.UUID) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        cursor = await connection.execute("SELECT * FROM catalog_service.products WHERE product_id=%s AND status!='DELETED'", (product_id,))
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return encode_product(row)
