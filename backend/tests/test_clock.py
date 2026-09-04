"""展示用虛擬時鐘（SPEC.md §4.10）。"""

from datetime import timedelta

from app.utils.virtual_clock import CLAMP_MAX, CLAMP_MIN, get_virtual_now, set_virtual_clock
from tests.helpers import login_headers, taipei

SEED_VIRTUAL_NOW = taipei(2026, 8, 24, 9, 0)


async def test_default_virtual_time_after_seed(pool):
    now = await get_virtual_now()

    assert abs((now - SEED_VIRTUAL_NOW).total_seconds()) < 60


async def test_set_virtual_now_offset_calculation(pool):
    target = taipei(2026, 8, 26, 14, 30)

    clamped = await set_virtual_clock(target)
    now = await get_virtual_now()

    assert abs((clamped - target).total_seconds()) < 1
    assert abs((now - target).total_seconds()) < 2


async def test_clamp_lower_bound(pool):
    clamped = await set_virtual_clock(taipei(2026, 8, 1, 0, 0))

    assert clamped == CLAMP_MIN


async def test_clamp_upper_bound(pool):
    clamped = await set_virtual_clock(taipei(2026, 9, 15, 0, 0))

    assert clamped == CLAMP_MAX


async def test_real_time_elapsing_keeps_virtual_time_in_range(pool):
    await set_virtual_clock(taipei(2026, 8, 30, 23, 0))

    now = await get_virtual_now()

    assert CLAMP_MIN <= now <= CLAMP_MAX


async def test_get_clock_requires_login(client):
    response = await client.get("/api/demo/clock")

    assert response.status_code == 401


async def test_get_clock_any_logged_in_role_allowed(client):
    for email in ("admin@demo.com", "manager@demo.com", "employee@demo.com"):
        headers = await login_headers(client, email)
        response = await client.get("/api/demo/clock", headers=headers)
        assert response.status_code == 200
        assert "virtual_now" in response.json()


async def test_put_clock_updates_virtual_now_any_role(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.put(
        "/api/demo/clock", headers=headers, json={"virtual_now": "2026-08-27T10:00:00+08:00"},
    )

    assert response.status_code == 200
    now = await get_virtual_now()
    assert abs((now - taipei(2026, 8, 27, 10, 0)).total_seconds()) < 2


async def test_put_clock_missing_field_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.put("/api/demo/clock", headers=headers, json={})

    assert response.status_code == 400


async def test_put_clock_out_of_range_gets_clamped_not_rejected(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.put(
        "/api/demo/clock", headers=headers, json={"virtual_now": "2026-09-15T00:00:00+08:00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["virtual_now"] == body["max"]


async def test_put_clock_drives_punch_in_business_timestamp(client):
    """時鐘不是獨立展示元件，是真的驅動業務時間戳（見 docs/PITFALLS.md B3）。"""
    headers = await login_headers(client, "employee@demo.com")
    await client.put("/api/demo/clock", headers=headers, json={"virtual_now": "2026-08-26T09:30:00+08:00"})

    response = await client.post("/api/attendance/punch-in", headers=headers)

    assert response.status_code == 201
    body = response.json()["attendance"]
    assert body["punch_date"] == "2026-08-26"
    assert body["punch_in_time"].startswith("2026-08-26T01:30:00")  # 台北 09:30 = UTC 01:30
