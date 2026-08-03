import base64
import logging
import time

import requests
from django.core.cache import cache
from django.conf import settings
import jwt

logger = logging.getLogger(__name__)


class VietQRTokenManager:
    """
    Manages VietQR Bearer token lifecycle:
    - Fetch token via Basic Auth
    - Cache with auto-refresh before expiration
    - Retry on network failures

    Coupling Level:
    - Data Coupling: Receives/returns defined token response DTOs only
    - Data Coupling: Reads config from settings only

    Cohesion Level:
    - Functional Cohesion: Single purpose - token lifecycle management

    Reason:
    Centralizing token management avoids duplicate code in gateway
    and keeps HTTP/caching concerns isolated from QR generation logic.
    """

    CACHE_KEY = "vietqr_access_token"
    MAX_RETRIES = 2
    RETRY_BACKOFF = 1  # seconds
    TOKEN_REFRESH_MARGIN = 60  # seconds

    def __init__(self):
        self.base_url = settings.VIETQR_BASE_URL
        self.username = settings.VIETQR_USERNAME
        self.password = settings.VIETQR_PASSWORD
        self.timeout = getattr(settings, "VIETQR_REQUEST_TIMEOUT", 10)

    def get_token(self) -> str:
        """
        Get valid Bearer token, using cached token if available and not expired.

        Returns:
            Bearer token string

        Raises:
            requests.RequestException: If all retries fail
        """
        return self.get_token_info()["token"]

    def get_token_info(self) -> dict:
        """
        Get a valid Bearer token plus non-sensitive expiration metadata.

        The token itself is returned for callers that need to authorize VietQR
        requests. Logs must only use the iat/exp/seconds_remaining fields.
        """
        # Try cached token first
        cached = cache.get(self.CACHE_KEY)
        if cached:
            token, expires_at = cached
            token_info = self._token_info(token, expires_at=expires_at)
            # Use if not expiring soon.
            if token_info["seconds_remaining"] >= self.TOKEN_REFRESH_MARGIN:
                logger.info(
                    "VietQR token cache hit iat=%s exp=%s seconds_remaining=%s",
                    token_info.get("iat"),
                    token_info.get("exp"),
                    token_info.get("seconds_remaining"),
                )
                return token_info

        # Fetch new token with retries
        for attempt in range(self.MAX_RETRIES):
            try:
                return self._fetch_token()
            except requests.RequestException as e:
                logger.warning(f"VietQR token fetch attempt {attempt + 1} failed: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BACKOFF * (2 ** attempt))
                else:
                    raise

    def _fetch_token(self) -> dict:
        """Fetch fresh token from VietQR."""
        auth = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()

        response = requests.post(
            f"{self.base_url}/vqr/api/token_generate",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 300)
        expires_at = time.time() + expires_in
        token_info = self._token_info(token, expires_at=expires_at)

        # Cache token with expiration
        cache_timeout = max(int(expires_in) - self.TOKEN_REFRESH_MARGIN, 1)
        cache.set(self.CACHE_KEY, (token, expires_at), cache_timeout)

        logger.info(
            "VietQR token fetched iat=%s exp=%s seconds_remaining=%s",
            token_info.get("iat"),
            token_info.get("exp"),
            token_info.get("seconds_remaining"),
        )
        return token_info

    def _token_info(self, token: str, *, expires_at: float | None = None) -> dict:
        now = int(time.time())
        metadata: dict = {"token": token, "iat": None, "exp": None}

        try:
            decoded = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
            metadata["iat"] = decoded.get("iat")
            metadata["exp"] = decoded.get("exp")
        except jwt.InvalidTokenError:
            logger.info("VietQR token metadata decode failed")

        if metadata["exp"] is not None:
            seconds_remaining = max(int(metadata["exp"]) - now, 0)
        elif expires_at is not None:
            seconds_remaining = max(int(expires_at - time.time()), 0)
        else:
            seconds_remaining = 0

        metadata["seconds_remaining"] = seconds_remaining
        return metadata
