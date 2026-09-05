"""AppSettings 的正式環境防呆（README.md 雲端部署章節、docs/PITFALLS.md G 節）。

這裡直接建構 AppSettings，不打 API、不碰資料庫——純粹驗證 pydantic 的
model_validator 邏輯，跟其餘測試檔的 client/db fixture 無關。
"""

import pytest

from app.config.settings import AppSettings


def _settings(**overrides):
    defaults = {
        "DATABASE_URL": "postgresql://x/y",
        "TEST_DATABASE_URL": "postgresql://x/y_test",
        "JWT_SECRET": "secret",
        "CORS_ORIGINS": "https://example.com",
        "ENVIRONMENT": "development",
    }
    return AppSettings(**{**defaults, **overrides})


def test_development_allows_wildcard_cors():
    settings = _settings(ENVIRONMENT="development", CORS_ORIGINS="*")

    assert settings.CORS_ORIGINS == "*"


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _settings(ENVIRONMENT="production", CORS_ORIGINS="*")


def test_production_rejects_empty_cors():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _settings(ENVIRONMENT="production", CORS_ORIGINS="   ")


def test_production_accepts_explicit_origin():
    settings = _settings(ENVIRONMENT="production", CORS_ORIGINS="https://app.example.com")

    assert settings.cors_origins_list == ["https://app.example.com"]
