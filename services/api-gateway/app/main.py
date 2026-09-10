"""Single external API entry point for the independently deployed services."""

from __future__ import annotations

import os
import uuid

import httpx
from fastapi import FastAPI, Request, Response

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


app = FastAPI(title="AIMS api-gateway", version="1.0.0")


@app.get("/healthz")
@app.get("/api/health/")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "api-gateway"}


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
