import pytest


@pytest.fixture(autouse=True)
def vietqr_test_settings(settings):
    settings.VIETQR_ENV = "test"
    settings.VIETQR_BASE_URL = "https://dev.vietqr.org"
    settings.VIETQR_USERNAME = "test-user"
    settings.VIETQR_PASSWORD = "test-pass"
    settings.VIETQR_BANK_CODE = "MB"
    settings.VIETQR_BANK_ACCOUNT = "0859246671"
    settings.VIETQR_USER_BANK_NAME = "Chu Tuan Linh"
    settings.VIETQR_CALLBACK_USERNAME = "test-user"
    settings.VIETQR_CALLBACK_PASSWORD = "test-pass"
    settings.VIETQR_CALLBACK_TOKEN_TTL_SECONDS = 300
    settings.VIETQR_REQUEST_TIMEOUT = 1
