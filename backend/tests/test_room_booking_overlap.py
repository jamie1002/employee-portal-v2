"""六種時段重疊拓撲 + 首尾相接放行（SPEC.md §4.6，半開區間 `[)`）。"""

import pytest

from tests.helpers import login_headers

MONDAY = "2026-08-24"


async def _seed_base_booking(client):
    """先建立 09:00–11:00 的既有預約（room_id=1）作為衝突判定基準。"""
    headers = await login_headers(client, "employee@demo.com")
    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "既有預約",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T11:00:00+08:00",
        },
    )
    assert response.status_code == 201
    return headers


TOPOLOGIES = [
    ("完全相同的時段", "09:00", "11:00", 409),
    ("新時段被既有時段包含", "09:30", "10:30", 409),
    ("新時段包含既有時段", "08:00", "12:00", 409),
    ("新時段搭到既有時段前緣", "08:00", "10:00", 409),
    ("新時段搭到既有時段後緣", "10:00", "12:00", 409),
    ("首尾相接（緊接在後）", "11:00", "12:00", 201),
    ("首尾相接（緊接在前）", "08:00", "09:00", 201),
]


@pytest.mark.parametrize("label,start,end,expected_status", TOPOLOGIES, ids=[t[0] for t in TOPOLOGIES])
async def test_overlap_topology(client, label, start, end, expected_status):
    headers = await _seed_base_booking(client)

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": label,
            "start_time": f"{MONDAY}T{start}:00+08:00", "end_time": f"{MONDAY}T{end}:00+08:00",
        },
    )

    assert response.status_code == expected_status
    if expected_status == 409:
        assert response.json()["error"]["code"] == "BOOKING_CONFLICT"


async def test_different_room_same_time_no_conflict(client):
    headers = await _seed_base_booking(client)

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 2, "title": "不同場地",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T11:00:00+08:00",
        },
    )

    assert response.status_code == 201


async def test_cancelled_existing_allows_reuse(client, db):
    headers = await _seed_base_booking(client)
    await db.execute("UPDATE room_bookings SET status = 'cancelled' WHERE room_id = 1")

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "重新預約",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T11:00:00+08:00",
        },
    )

    assert response.status_code == 201


async def test_conflict_message_contains_slot_and_name(client):
    headers = await _seed_base_booking(client)

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "衝突",
            "start_time": f"{MONDAY}T10:00:00+08:00", "end_time": f"{MONDAY}T12:00:00+08:00",
        },
    )

    message = response.json()["error"]["message"]
    assert "09:00" in message
    assert "11:00" in message
    assert "陳小華" in message
