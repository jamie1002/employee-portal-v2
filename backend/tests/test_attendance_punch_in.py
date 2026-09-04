"""上班打卡的整合測試（打真實 PostgreSQL）。"""

import asyncio
from datetime import date, datetime

from app.utils.pg_types import pg_date
from app.utils.virtual_clock import set_virtual_clock
from tests.helpers import EMPLOYEE_ID, login_headers, taipei

MONDAY = date(2026, 8, 24)
SATURDAY = date(2026, 8, 29)


async def test_first_punch_in_creates_record(client):
    await set_virtual_clock(taipei(2026, 8, 24, 9, 5))
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/attendance/punch-in", headers=headers)

    assert response.status_code == 201
    attendance = response.json()["attendance"]
    assert attendance["punch_date"] == MONDAY.isoformat()
    assert attendance["status"] == "normal"
    assert attendance["has_punched_in"] is True
    assert attendance["has_punched_out"] is False
    assert attendance["is_workday"] is True


async def test_punch_in_after_grace_is_marked_late(client):
    await set_virtual_clock(taipei(2026, 8, 24, 9, 11))
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/attendance/punch-in", headers=headers)

    assert response.json()["attendance"]["status"] == "late"


async def test_punch_in_at_grace_boundary_with_seconds_is_still_normal(client):
    """09:10:59 與 09:10:00 都是「9 點 10 分」，不該因為秒數判成不同結果。"""
    await set_virtual_clock(taipei(2026, 8, 24, 9, 10, 59))
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/attendance/punch-in", headers=headers)

    assert response.json()["attendance"]["status"] == "normal"


async def test_duplicate_punch_in_returns_409_and_keeps_original_time(client, db):
    headers = await login_headers(client, "employee@demo.com")
    first = await client.post("/api/attendance/punch-in", headers=headers)
    assert first.status_code == 201

    second = await client.post("/api/attendance/punch-in", headers=headers)

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ALREADY_PUNCHED_IN"
    stored = await db.fetchval(
        "SELECT punch_in_time FROM attendances WHERE user_id = $1 AND punch_date = $2",
        EMPLOYEE_ID,
        pg_date(MONDAY),
    )
    original = datetime.fromisoformat(first.json()["attendance"]["punch_in_time"])
    assert stored == original


async def test_punch_in_without_token_returns_401(client):
    response = await client.post("/api/attendance/punch-in")

    assert response.status_code == 401


async def test_smuggled_user_id_in_body_is_ignored(client, db):
    """打卡對象一律取自 token，請求主體裡夾帶的 user_id 不得生效。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/attendance/punch-in", headers=headers, json={"user_id": 1})

    assert response.status_code == 201
    owner = await db.fetchval(
        "SELECT user_id FROM attendances WHERE id = $1", response.json()["attendance"]["id"]
    )
    assert owner == EMPLOYEE_ID


async def test_concurrent_punch_in_exactly_one_succeeds(client, db):
    """兩個並行請求可能同時通過應用層的「今天打過了嗎」檢查，此時要靠
    UNIQUE(user_id, punch_date) 擋下第二筆，並轉譯成 409 而不是 500。"""
    headers = await login_headers(client, "employee@demo.com")

    first, second = await asyncio.gather(
        client.post("/api/attendance/punch-in", headers=headers),
        client.post("/api/attendance/punch-in", headers=headers),
    )

    assert sorted([first.status_code, second.status_code]) == [201, 409]
    count = await db.fetchval(
        "SELECT count(*) FROM attendances WHERE user_id = $1 AND punch_date = $2",
        EMPLOYEE_ID,
        pg_date(MONDAY),
    )
    assert count == 1


async def test_weekend_punch_in_is_holiday_work(client):
    await set_virtual_clock(taipei(2026, 8, 29, 9, 0))  # 週六
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/attendance/punch-in", headers=headers)

    attendance = response.json()["attendance"]
    assert attendance["punch_date"] == SATURDAY.isoformat()
    assert attendance["status"] == "holiday_work"
    assert attendance["is_workday"] is False


async def test_national_holiday_punch_in_is_holiday_work(client, db):
    await db.execute(
        "INSERT INTO holidays (holiday_date, name) VALUES ($1, '測試用假日') ON CONFLICT DO NOTHING",
        pg_date(date(2026, 8, 26)),
    )
    await set_virtual_clock(taipei(2026, 8, 26, 9, 0))
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/attendance/punch-in", headers=headers)

    assert response.json()["attendance"]["status"] == "holiday_work"
    assert response.json()["attendance"]["is_workday"] is False


async def test_punch_date_uses_taipei_business_date_not_utc(client):
    """台北 00:30 對應 UTC 前一日 16:30，營業日必須是台北的今天。"""
    await set_virtual_clock(taipei(2026, 8, 25, 0, 30))
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/attendance/punch-in", headers=headers)

    assert response.json()["attendance"]["punch_date"] == "2026-08-25"
