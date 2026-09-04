"""兩層防護的並行競態驗證（SPEC.md §4.6：應用層預檢 + DB 排除約束）。"""

import asyncio
from unittest.mock import AsyncMock, patch

from tests.helpers import login_headers

MONDAY = "2026-08-24"


async def test_concurrent_same_slot_exactly_one_succeeds(client, db):
    employee_headers = await login_headers(client, "employee@demo.com")
    manager_headers = await login_headers(client, "manager@demo.com")

    payload = {
        "room_id": 3, "title": "搶同一時段",
        "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
    }

    response_a, response_b = await asyncio.gather(
        client.post("/api/room-bookings", headers=employee_headers, json=payload),
        client.post("/api/room-bookings", headers=manager_headers, json=payload),
    )

    statuses = sorted([response_a.status_code, response_b.status_code])
    assert statuses == [201, 409]
    assert response_a.status_code < 500
    assert response_b.status_code < 500

    count = await db.fetchval(
        "SELECT count(*) FROM room_bookings WHERE room_id = 3 AND status = 'confirmed'"
    )
    assert count == 1


async def test_bypassing_precheck_still_hits_db_constraint(client):
    """就算應用層預檢失效（被繞過），資料庫排除約束仍是最後防線——不是 500。"""
    headers = await login_headers(client, "employee@demo.com")
    first = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 2, "title": "第一筆",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )
    assert first.status_code == 201

    from app.repositories import room_booking_repository

    with patch.object(room_booking_repository, "find_conflicts", new=AsyncMock(return_value=[])):
        second = await client.post(
            "/api/room-bookings", headers=headers,
            json={
                "room_id": 2, "title": "第二筆（預檢已被繞過）",
                "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
            },
        )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "23P01"
