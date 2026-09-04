"""展示資料一鍵重置（SPEC.md §4.11）。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.config.tables import BUSINESS_TABLES
from app.services import demo as demo_service
from tests.helpers import login_headers


async def test_admin_reset_returns_counts(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post("/api/demo/reset", headers=headers)

    assert response.status_code == 200
    counts = response.json()["counts"]
    assert set(counts.keys()) == set(BUSINESS_TABLES)
    assert counts["users"] == 6


async def test_non_admin_forbidden_no_change(client, db):
    manager_headers = await login_headers(client, "manager@demo.com")
    employee_headers = await login_headers(client, "employee@demo.com")

    manager_res = await client.post("/api/demo/reset", headers=manager_headers)
    employee_res = await client.post("/api/demo/reset", headers=employee_headers)
    no_auth_res = await client.post("/api/demo/reset")

    assert manager_res.status_code == 403
    assert employee_res.status_code == 403
    assert no_auth_res.status_code == 401
    count = await db.fetchval("SELECT count(*) FROM users")
    assert count == 6


async def test_extra_data_removed_after_reset(client, db):
    headers = await login_headers(client, "admin@demo.com")
    await db.execute(
        "INSERT INTO room_bookings (room_id, user_id, title, start_time, end_time) "
        "VALUES (1, 3, '額外預約', '2026-08-24T09:00:00+08:00', '2026-08-24T10:00:00+08:00')"
    )

    response = await client.post("/api/demo/reset", headers=headers)

    assert response.status_code == 200
    row = await db.fetchrow("SELECT id FROM room_bookings WHERE title = '額外預約'")
    assert row is None


async def test_demo_accounts_locked_and_first_login_false_after_reset(client):
    headers = await login_headers(client, "admin@demo.com")

    await client.post("/api/demo/reset", headers=headers)

    for email in ("admin@demo.com", "manager@demo.com", "employee@demo.com"):
        login_res = await client.post("/api/auth/login", json={"email": email, "password": "Demo1234"})
        assert login_res.status_code == 200
        assert login_res.json()["user"]["is_first_login"] is False


async def test_id_restarts_after_reset_restart_identity(client):
    headers = await login_headers(client, "admin@demo.com")

    await client.post("/api/demo/reset", headers=headers)
    create_res = await client.post(
        "/api/users", headers=headers,
        json={"name": "新員工", "email": "new-after-reset@demo.com", "role": "employee", "department_id": 1, "password": "Demo1234"},
    )

    assert create_res.json()["user"]["id"] == 7


async def test_reset_twice_succeeds_with_same_result(client):
    headers = await login_headers(client, "admin@demo.com")

    first = await client.post("/api/demo/reset", headers=headers)
    second = await client.post("/api/demo/reset", headers=headers)

    assert first.json()["counts"] == second.json()["counts"]


async def test_seed_failure_rolls_back_everything(pool):
    """種子寫入失敗時，連同前面的 TRUNCATE 一併回滾——不能留下業務資料已清空
    但新資料沒寫進去的半殘狀態。直接測 service 層而不透過 HTTP：多層
    BaseHTTPMiddleware 疊加時，httpx 的 ASGITransport 會讓例外原封不動地
    往外拋，不會走到 FastAPI 註冊的例外處理器，這是測試環境本身的限制，
    與這裡真正要驗證的交易回滾行為無關。"""
    with patch("app.db_scripts.seed.seed_business_data", new=AsyncMock(side_effect=RuntimeError("模擬寫入失敗"))):
        with pytest.raises(RuntimeError):
            await demo_service.reset_demo_data(pool)

    count = await pool.fetchval("SELECT count(*) FROM users")
    assert count == 6
