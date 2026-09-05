"""下班打卡的整合測試：工時計算、早退判定、回應必備欄位。"""

import asyncio
from datetime import datetime, timedelta

from app.utils.virtual_clock import set_virtual_clock
from tests.helpers import login_headers, taipei


async def _punch_in_at(client, headers, moment):
    await set_virtual_clock(moment)
    response = await client.post("/api/attendance/punch-in", headers=headers)
    assert response.status_code == 201
    return response.json()["attendance"]


async def _punch_out_at(client, headers, moment):
    await set_virtual_clock(moment)
    return await client.post("/api/attendance/punch-out", headers=headers)


async def test_punch_out_without_punch_in_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/attendance/punch-out", headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NOT_PUNCHED_IN"


async def test_full_day_work_hours_are_eight(client):
    """09:05 上班／18:10 下班：正常工時結束 18:05，扣掉浮動午休正好 8 小時。"""
    headers = await login_headers(client, "employee@demo.com")
    await _punch_in_at(client, headers, taipei(2026, 8, 24, 9, 5))

    response = await _punch_out_at(client, headers, taipei(2026, 8, 24, 18, 10))

    assert response.status_code == 200
    attendance = response.json()["attendance"]
    assert attendance["work_hours"] == "8.00"
    assert attendance["has_punched_out"] is True
    assert attendance["is_early_leave"] is False


async def test_late_arrival_work_hours_are_capped(client):
    """09:23 上班（遲到超過緩衝）：正常工時封頂在 18:10，工時 7.78 而非計滿 8 小時。"""
    headers = await login_headers(client, "employee@demo.com")
    await _punch_in_at(client, headers, taipei(2026, 8, 24, 9, 23))

    response = await _punch_out_at(client, headers, taipei(2026, 8, 24, 18, 23))

    assert response.json()["attendance"]["work_hours"] == "7.78"
    assert response.json()["attendance"]["status"] == "late"


async def test_duplicate_punch_out_returns_409(client):
    headers = await login_headers(client, "employee@demo.com")
    await _punch_in_at(client, headers, taipei(2026, 8, 24, 9, 0))
    await _punch_out_at(client, headers, taipei(2026, 8, 24, 18, 0))

    response = await _punch_out_at(client, headers, taipei(2026, 8, 24, 18, 30))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_PUNCHED_OUT"


async def test_concurrent_punch_out_exactly_one_succeeds(client, db):
    """跟 test_attendance_punch_in.py 的並行上班打卡測試同一類風險：兩個並行的
    下班打卡請求都可能通過應用層的「今天下班了嗎」檢查，要靠 upsert_attendance()
    的原子 guard（require_field_null）擋下第二筆，而不是兩個都成功。"""
    headers = await login_headers(client, "employee@demo.com")
    await _punch_in_at(client, headers, taipei(2026, 8, 24, 9, 0))
    await set_virtual_clock(taipei(2026, 8, 24, 18, 0))

    first, second = await asyncio.gather(
        client.post("/api/attendance/punch-out", headers=headers),
        client.post("/api/attendance/punch-out", headers=headers),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    stored = await db.fetchrow(
        "SELECT punch_in_time, punch_out_time FROM attendances "
        "WHERE user_id = (SELECT id FROM users WHERE email = 'employee@demo.com') "
        "AND punch_date = '2026-08-24'"
    )
    assert stored["punch_in_time"] is not None
    assert stored["punch_out_time"] is not None


async def test_response_carries_thresholds_for_the_frontend(client):
    """晚下班提示與加班起算點一律由後端算出，前端不得自行推算（SPEC.md §4.1.6）。"""
    headers = await login_headers(client, "employee@demo.com")
    await _punch_in_at(client, headers, taipei(2026, 8, 24, 9, 0))

    response = await _punch_out_at(client, headers, taipei(2026, 8, 24, 18, 0))

    attendance = response.json()["attendance"]
    normal_end = datetime.fromisoformat(attendance["normal_work_end"])
    assert normal_end == taipei(2026, 8, 24, 18, 0)
    assert datetime.fromisoformat(attendance["late_punch_out_threshold"]) == normal_end + timedelta(hours=1)
    assert datetime.fromisoformat(attendance["overtime_eligible_start"]) == normal_end + timedelta(minutes=30)
    assert attendance["is_workday"] is True


async def test_leaving_one_minute_early_is_early_leave(client):
    """早退零寬限：17:59 下班就是早退，18:00 整不是。"""
    headers = await login_headers(client, "employee@demo.com")
    await _punch_in_at(client, headers, taipei(2026, 8, 24, 9, 0))

    response = await _punch_out_at(client, headers, taipei(2026, 8, 24, 17, 59))

    assert response.json()["attendance"]["is_early_leave"] is True


async def test_leaving_exactly_at_normal_end_is_not_early_leave(client):
    headers = await login_headers(client, "employee@demo.com")
    await _punch_in_at(client, headers, taipei(2026, 8, 24, 9, 0))

    response = await _punch_out_at(client, headers, taipei(2026, 8, 24, 18, 0))

    assert response.json()["attendance"]["is_early_leave"] is False


async def test_non_workday_counts_full_time_and_eligible_start_is_punch_in(client):
    headers = await login_headers(client, "employee@demo.com")
    await _punch_in_at(client, headers, taipei(2026, 8, 29, 9, 0))  # 週六

    response = await _punch_out_at(client, headers, taipei(2026, 8, 29, 15, 0))

    attendance = response.json()["attendance"]
    assert attendance["is_workday"] is False
    assert attendance["is_early_leave"] is False
    # 09:00–15:00 共 6 小時，扣掉與表定午休重疊的 1 小時。
    assert attendance["work_hours"] == "5.00"
    assert datetime.fromisoformat(attendance["overtime_eligible_start"]) == taipei(2026, 8, 29, 9, 0)
