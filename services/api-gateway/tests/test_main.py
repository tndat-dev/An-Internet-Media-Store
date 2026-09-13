import asyncio

from fastapi.testclient import TestClient

from app.main import RedisRateLimiter, app, upstream_for


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "api-gateway"


def test_prometheus_metrics_are_exposed():
    with TestClient(app) as client:
        client.get("/healthz")
        response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_domain_routing_is_explicit():
    assert upstream_for("/api/products/").startswith("http://catalog-service")
    assert upstream_for("/api/search/").startswith("http://search-recommendation-service")
    assert upstream_for("/api/unknown/") is None


def test_redis_rate_limit_blocks_after_window_limit():
    class Redis:
        value = 0

        async def incr(self, _):
            self.value += 1
            return self.value

        async def expire(self, *_):
            return True

    limiter = RedisRateLimiter()
    limiter.client = Redis()
    limiter.ready = True
    limiter.limit = 1
    assert asyncio.run(limiter.allow("client"))[0] is True
    assert asyncio.run(limiter.allow("client"))[0] is False
