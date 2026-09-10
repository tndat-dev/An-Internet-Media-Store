"""Cart ownership with product snapshots obtained through service APIs."""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import httpx
import psycopg
from fastapi import FastAPI, Header, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS cart_service;
CREATE TABLE IF NOT EXISTS cart_service.carts (
  cart_id uuid PRIMARY KEY, cart_token text UNIQUE NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE', updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cart_service.items (
  cart_item_id uuid PRIMARY KEY, cart_id uuid NOT NULL REFERENCES cart_service.carts(cart_id) ON DELETE CASCADE,
  product_id text NOT NULL, product_title text NOT NULL, product_type text NOT NULL,
  image_url text NOT NULL DEFAULT '', unit_price numeric(14,2) NOT NULL,
  quantity integer NOT NULL CHECK(quantity > 0), UNIQUE(cart_id, product_id)
);
"""


class ItemMutation(BaseModel):
    productId: str | None = None
    quantity: int = Field(ge=1, le=100)


class CartRuntime:
    def __init__(self) -> None:
        self.database_url = os.getenv("CART_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
        self.ready = False

    async def start(self) -> None:
        if not self.database_url:
            return
        async with await psycopg.AsyncConnection.connect(self.database_url) as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext('aims-cart-schema-v1'))")
            await connection.execute(SCHEMA_SQL)
        self.ready = True

    async def connect(self) -> psycopg.AsyncConnection:
        if not self.database_url:
            raise HTTPException(status_code=503, detail="Cart database unavailable")
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)


runtime = CartRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield


app = FastAPI(title="AIMS cart-service", version="1.0.0", lifespan=lifespan)


async def product_snapshot(product_id: str) -> dict[str, Any]:
    base = os.getenv("CATALOG_SERVICE_URL", "http://catalog-service.production.svc.cluster.local:8000")
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(f"{base}/api/products/{product_id}/")
    if response.status_code != 200:
        raise HTTPException(status_code=409, detail="Product is unavailable")
    return response.json()


async def ensure_cart(connection: psycopg.AsyncConnection, token: str) -> uuid.UUID:
    cursor = await connection.execute(
        "INSERT INTO cart_service.carts(cart_id,cart_token) VALUES (%s,%s) ON CONFLICT(cart_token) DO UPDATE SET updated_at=now() RETURNING cart_id",
        (uuid.uuid4(), token),
    )
    return (await cursor.fetchone())["cart_id"]


def render_cart(cart: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    rendered = []
    subtotal = Decimal("0")
    for item in items:
        line = item["unit_price"] * item["quantity"]
        subtotal += line
        rendered.append({
            "cartItemId": str(item["cart_item_id"]), "productId": item["product_id"],
            "productTitle": item["product_title"], "productType": item["product_type"],
            "imageUrl": item["image_url"], "unitPrice": str(item["unit_price"]),
            "quantity": item["quantity"], "lineSubtotal": str(line), "stockQuantity": 999,
            "productStatus": "ACTIVE", "stockWarning": None,
        })
    return {"cartId": str(cart["cart_id"]), "cartToken": cart["cart_token"], "status": cart["status"],
            "items": rendered, "subtotalExclVat": str(subtotal),
            "totalItems": sum(item["quantity"] for item in items), "canPlaceOrder": bool(items), "stockErrors": []}


async def load_cart(token: str) -> dict[str, Any]:
    async with await runtime.connect() as connection:
        cart_id = await ensure_cart(connection, token)
        cart_cursor = await connection.execute("SELECT * FROM cart_service.carts WHERE cart_id=%s", (cart_id,))
        cart = await cart_cursor.fetchone()
        item_cursor = await connection.execute("SELECT * FROM cart_service.items WHERE cart_id=%s ORDER BY product_title", (cart_id,))
        items = await item_cursor.fetchall()
    return render_cart(cart, items)


def require_token(value: str | None) -> str:
    if not value:
        raise HTTPException(status_code=400, detail="X-Cart-Token is required")
    return value


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "cart-service", "databaseReady": runtime.ready}


@app.get("/api/cart/")
async def get_cart(x_cart_token: str | None = Header(default=None)) -> dict[str, Any]:
    return await load_cart(require_token(x_cart_token))


@app.post("/api/cart/items/")
async def add_item(payload: ItemMutation, x_cart_token: str | None = Header(default=None)) -> dict[str, Any]:
    token = require_token(x_cart_token)
    if not payload.productId:
        raise HTTPException(status_code=422, detail="productId is required")
    product = await product_snapshot(payload.productId)
    async with await runtime.connect() as connection:
        cart_id = await ensure_cart(connection, token)
        await connection.execute(
            "INSERT INTO cart_service.items(cart_item_id,cart_id,product_id,product_title,product_type,image_url,unit_price,quantity) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(cart_id,product_id) DO UPDATE SET quantity=cart_service.items.quantity+EXCLUDED.quantity",
            (uuid.uuid4(), cart_id, payload.productId, product.get("title", "Product"), product.get("product_type", "UNKNOWN"), product.get("image_url", ""), Decimal(str(product["price"])), payload.quantity),
        )
    return await load_cart(token)


@app.patch("/api/cart/items/{item_id}/")
async def update_item(item_id: uuid.UUID, payload: ItemMutation, x_cart_token: str | None = Header(default=None)) -> dict[str, Any]:
    token = require_token(x_cart_token)
    async with await runtime.connect() as connection:
        await connection.execute("UPDATE cart_service.items SET quantity=%s WHERE cart_item_id=%s AND cart_id=(SELECT cart_id FROM cart_service.carts WHERE cart_token=%s)", (payload.quantity, item_id, token))
    return await load_cart(token)


@app.delete("/api/cart/items/{item_id}/")
async def delete_item(item_id: uuid.UUID, x_cart_token: str | None = Header(default=None)) -> dict[str, Any]:
    token = require_token(x_cart_token)
    async with await runtime.connect() as connection:
        await connection.execute("DELETE FROM cart_service.items WHERE cart_item_id=%s AND cart_id=(SELECT cart_id FROM cart_service.carts WHERE cart_token=%s)", (item_id, token))
    return await load_cart(token)
