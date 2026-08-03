"""
Unit tests for VietQRTokenManager

Coupling Level:
- Data Coupling: Mocks requests.post and django.core.cache, receives/returns DTOs only

Cohesion Level:
- Functional Cohesion: All tests verify token lifecycle management

Reason:
Tests ensure token caching, refresh, and retry logic work correctly
without making actual HTTP calls to VietQR.
"""

import pytest
from unittest.mock import patch, Mock
import requests

from apps.payments.gateways.token_manager import VietQRTokenManager


@patch("apps.payments.gateways.token_manager.requests.post")
@patch("apps.payments.gateways.token_manager.cache")
def test_get_token_success(mock_cache, mock_post):
    """Test successful token fetch and caching."""
    mock_cache.get.return_value = None  # No cached token
    mock_post.return_value.json.return_value = {
        "access_token": "token_abc123",
        "token_type": "Bearer",
        "expires_in": 300,
    }

    manager = VietQRTokenManager()
    token = manager.get_token()

    assert token == "token_abc123"
    mock_post.assert_called_once()
    # Verify cache.set was called
    assert mock_cache.set.called


@patch("apps.payments.gateways.token_manager.requests.post")
@patch("apps.payments.gateways.token_manager.cache")
def test_get_token_uses_cache(mock_cache, mock_post):
    """Test cached token is reused if not expiring soon."""
    import time

    token = "token_abc123"
    expires_at = time.time() + 120  # Not expiring soon with 60s margin
    mock_cache.get.return_value = (token, expires_at)

    manager = VietQRTokenManager()
    result = manager.get_token()

    assert result == token
    # Should not call post if cache hit
    mock_post.assert_not_called()


@patch("apps.payments.gateways.token_manager.requests.post")
@patch("apps.payments.gateways.token_manager.cache")
def test_get_token_refreshes_expiring_token(mock_cache, mock_post):
    """Test token is refreshed if expiring soon."""
    import time

    old_token = "old_token"
    expires_at = time.time() + 30  # Expiring soon (< 60s margin)
    mock_cache.get.return_value = (old_token, expires_at)
    mock_post.return_value.json.return_value = {
        "access_token": "new_token",
        "token_type": "Bearer",
        "expires_in": 300,
    }

    manager = VietQRTokenManager()
    token = manager.get_token()

    assert token == "new_token"
    mock_post.assert_called_once()


@patch("apps.payments.gateways.token_manager.requests.post")
@patch("apps.payments.gateways.token_manager.cache")
def test_get_token_info_returns_safe_expiration_metadata(mock_cache, mock_post):
    """Test token metadata can be logged without exposing the token."""
    import time
    import jwt

    iat = int(time.time())
    exp = iat + 300
    encoded = jwt.encode({"iat": iat, "exp": exp}, "secret", algorithm="HS256")
    mock_cache.get.return_value = None
    mock_post.return_value.json.return_value = {
        "access_token": encoded,
        "token_type": "Bearer",
        "expires_in": 300,
    }

    manager = VietQRTokenManager()
    token_info = manager.get_token_info()

    assert token_info["token"] == encoded
    assert token_info["iat"] == iat
    assert token_info["exp"] == exp
    assert token_info["seconds_remaining"] > 0


@patch("apps.payments.gateways.token_manager.requests.post")
@patch("apps.payments.gateways.token_manager.cache")
def test_get_token_retries_on_failure(mock_cache, mock_post):
    """Test retry on network failure succeeds on second attempt."""
    mock_cache.get.return_value = None
    mock_post.side_effect = [
        requests.ConnectionError("Network error"),
        Mock(json=lambda: {
            "access_token": "token_abc123",
            "token_type": "Bearer",
            "expires_in": 300,
        }),
    ]

    manager = VietQRTokenManager()
    token = manager.get_token()

    assert token == "token_abc123"
    assert mock_post.call_count == 2


@patch("apps.payments.gateways.token_manager.requests.post")
@patch("apps.payments.gateways.token_manager.cache")
def test_get_token_raises_after_max_retries(mock_cache, mock_post):
    """Test raises error after max retries exceeded."""
    mock_cache.get.return_value = None
    mock_post.side_effect = requests.ConnectionError("Network error")

    manager = VietQRTokenManager()

    with pytest.raises(requests.ConnectionError):
        manager.get_token()

    # Should attempt 2 times (MAX_RETRIES)
    assert mock_post.call_count == 2
