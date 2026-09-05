"""統一錯誤處理：PostgreSQL 錯誤碼與未預期例外一律轉譯為 {"error": {"message", "code"}}
格式，不得外洩成未經轉譯的原始例外（見 SPEC.md §7.1）。

用一個獨立、乾淨的 FastAPI app（只掛 error_handler.py 的例外處理器，不掛
main.py 的其他 middleware）驗證轉譯本身，不依賴真實資料庫或業務端點。
"""
import asyncpg
import pytest
from asyncpg.exceptions import ExclusionViolationError, ForeignKeyViolationError, UniqueViolationError
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.error_handler import register_error_handlers
from app.utils.errors import AppError


def _build_test_app() -> FastAPI:
    test_app = FastAPI()
    register_error_handlers(test_app)

    @test_app.get("/unique-violation")
    async def _unique_violation():
        raise UniqueViolationError("duplicate key value violates unique constraint")

    @test_app.get("/exclusion-violation")
    async def _exclusion_violation():
        raise ExclusionViolationError("conflicting key value violates exclusion constraint")

    @test_app.get("/foreign-key-violation")
    async def _fk_violation():
        raise ForeignKeyViolationError("insert or update violates foreign key constraint")

    @test_app.get("/app-error")
    async def _app_error():
        raise AppError(403, "你沒有權限執行此操作。", "FORBIDDEN")

    @test_app.get("/unexpected")
    async def _unexpected():
        raise RuntimeError("SELECT * FROM secret_table WHERE 1=1")

    return test_app


@pytest.fixture
async def error_client():
    transport = ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def test_unique_violation_maps_to_409(error_client):
    response = await error_client.get("/unique-violation")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "23505"
    assert "select" not in response.json()["error"]["message"].lower()
    assert "constraint" not in response.json()["error"]["message"].lower()


async def test_exclusion_violation_maps_to_409(error_client):
    response = await error_client.get("/exclusion-violation")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "23P01"


async def test_foreign_key_violation_maps_to_400(error_client):
    response = await error_client.get("/foreign-key-violation")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "23503"


async def test_app_error_uses_its_status_code(error_client):
    response = await error_client.get("/app-error")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_unexpected_error_returns_500_without_leaking_details(error_client):
    response = await error_client.get("/unexpected")

    assert response.status_code == 500
    assert "select" not in response.text.lower()
    assert "secret_table" not in response.text.lower()
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


async def test_asyncpg_error_base_classes_are_still_registered():
    """register_error_handlers() 掛的是具體例外類別，確認 asyncpg 版本升級後
    這三個類別仍然存在且確實是 Exception 的子類別，不是靜默失效。"""
    for exc_cls in (UniqueViolationError, ExclusionViolationError, ForeignKeyViolationError):
        assert issubclass(exc_cls, asyncpg.PostgresError)
