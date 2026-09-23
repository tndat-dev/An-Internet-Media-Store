from fastapi.testclient import TestClient

from app.main import RegisterRequest, app, hash_password, token_digest, token_from_header, verify_password


def test_health_without_database_is_degraded(monkeypatch):
    monkeypatch.delenv("AUTH_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "service": "auth-service", "databaseReady": False}


def test_password_hash_round_trip_and_random_salt():
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)
    assert not verify_password("anything", "unsupported")


def test_token_header_and_digest_contract():
    assert token_from_header("Token opaque-token") == "opaque-token"
    assert token_from_header("Bearer opaque-token") == "opaque-token"
    assert token_digest("opaque-token") == token_digest("opaque-token")


def test_registration_contract_defaults():
    payload = RegisterRequest(username="buyer", email="buyer@example.test", password="secret123")
    assert payload.fullName == ""
    assert payload.phone == ""
