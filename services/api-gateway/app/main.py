"""Single external API entry point for the independently deployed services."""

from __future__ import annotations

import os
import asyncio
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio.sentinel import Sentinel

from app.observability import install_observability

SERVICE_ROUTES = {
    "auth": "auth-service",
    "admin": "auth-service",
    "products": "catalog-service",
    "cart": "cart-service",
    "orders": "order-service",
    "payments": "payment-service",
    "inventory": "inventory-service",
    "notifications": "notification-service",
    "search": "search-recommendation-service",
    "recommendations": "search-recommendation-service",
    "security": "security-telemetry-service",
}


def upstream_for(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) < 2 or parts[0] != "api":
        return None
    service = SERVICE_ROUTES.get(parts[1])
    if service is None:
        return None
    override = os.getenv(f"{service.replace('-', '_').upper()}_URL")
    return override or f"http://{service}.production.svc.cluster.local:8000"


class RedisRateLimiter:
    """Sentinel-backed fixed-window limiter; fails open during Redis recovery."""

    def __init__(self) -> None:
        self.client = None
        self.ready = False
        self.limit = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "300"))
        self.retry_at = 0.0
        self.reconnect_lock = asyncio.Lock()

    async def start(self) -> None:
        host = os.getenv("REDIS_HOST", "").strip()
        password = os.getenv("REDIS_PASSWORD", "")
        if not host or not password:
            return
        sentinel = Sentinel(
            [(host, int(os.getenv("REDIS_PORT", "26379")))],
            password=password,
            sentinel_kwargs={"password": password},
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self.client = sentinel.master_for(
            os.getenv("REDIS_SENTINEL_MASTER", "myMaster"),
            password=password,
            decode_responses=True,
        )
        await self.client.ping()
        self.ready = True

    async def stop(self) -> None:
        if self.client:
            await self.client.aclose()

    async def allow(self, subject: str) -> tuple[bool, int]:
        if not self.ready and time.monotonic() >= self.retry_at:
            async with self.reconnect_lock:
                if not self.ready and time.monotonic() >= self.retry_at:
                    self.retry_at = time.monotonic() + 5
                    try:
                        await self.start()
                    except Exception:
                        self.ready = False
        if not self.ready or not self.client:
            return True, 0
        window = int(time.time() // 60)
        key = f"aims:rate-limit:{window}:{subject}"
        try:
            value = await self.client.incr(key)
            if value == 1:
                await self.client.expire(key, 120)
            return value <= self.limit, max(0, 60 - int(time.time()) % 60)
        except Exception:
            self.ready = False
            self.retry_at = time.monotonic() + 5
            return True, 0


rate_limiter = RedisRateLimiter()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await rate_limiter.start()
    except Exception:
        rate_limiter.ready = False
    yield
    await rate_limiter.stop()


app = FastAPI(title="AIMS api-gateway", version="1.1.0", lifespan=lifespan)
install_observability(app)


@app.middleware("http")
async def enforce_rate_limit(request: Request, call_next):
    if request.url.path in {"/healthz", "/api/health/", "/metrics"}:
        return await call_next(request)
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    subject = forwarded or (request.client.host if request.client else "unknown")
    allowed, retry_after = await rate_limiter.allow(subject)
    if not allowed:
        return JSONResponse(
            {"detail": "Rate limit exceeded"},
            status_code=429,
            headers={"retry-after": str(retry_after)},
        )
    response = await call_next(request)
    response.headers["x-aims-rate-limit"] = "redis" if rate_limiter.ready else "fail-open"
    return response


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "api-gateway",
        "redisRateLimiter": "ready" if rate_limiter.ready else "fail-open",
    }


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(path: str, request: Request) -> Response:
    full_path = f"/api/{path}"
    upstream = upstream_for(full_path)
    if upstream is None:
        return Response(content='{"detail":"Unknown API route"}', status_code=404, media_type="application/json")

    correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    forwarded_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in {"authorization", "content-type", "accept", "x-cart-token", "user-agent"}
    }
    forwarded_headers["x-correlation-id"] = correlation_id
    forwarded_headers["x-forwarded-host"] = request.headers.get("host", "")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            result = await client.request(
                request.method,
                f"{upstream}{full_path}",
                params=request.query_params,
                content=await request.body(),
                headers=forwarded_headers,
            )
    except httpx.HTTPError as error:
        return Response(
            content=f'{{"detail":"Upstream unavailable","correlationId":"{correlation_id}"}}',
            status_code=503,
            media_type="application/json",
            headers={"x-correlation-id": correlation_id},
        )

    response_headers = {"x-correlation-id": correlation_id}
    content_type = result.headers.get("content-type")
    if content_type:
        response_headers["content-type"] = content_type
    return Response(content=result.content, status_code=result.status_code, headers=response_headers)
