"""考勤設定（SPEC.md §6.6）。"""

import asyncpg
import pytest

from tests.helpers import login_headers

DEFAULT_PAYLOAD = {
    "work_start_time": "09:00", "work_end_time": "18:00",
    "lunch_start_time": "12:00", "lunch_end_time": "13:00",
    "grace_period_minutes": 10,
}


async def test_get_settings_ok(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/settings", headers=headers)

    assert response.status_code == 200
    assert response.json()["settings"]["work_start_time"] == "09:00:00"


async def test_get_settings_requires_auth(client):
    response = await client.get("/api/settings")

    assert response.status_code == 401


async def test_admin_update_settings(client):
    headers = await login_headers(client, "admin@demo.com")
    payload = {**DEFAULT_PAYLOAD, "work_start_time": "08:30", "work_end_time": "17:30", "grace_period_minutes": 15}

    response = await client.put("/api/settings", headers=headers, json=payload)

    assert response.status_code == 200
    assert response.json()["settings"]["work_start_time"] == "08:30:00"
    assert response.json()["settings"]["grace_period_minutes"] == 15


async def test_permission_holder_can_update(client):
    admin_headers = await login_headers(client, "admin@demo.com")
    await client.put(
        "/api/users/3/permissions", headers=admin_headers, json={"permissions": ["settings.manage"]},
    )
    grantee_headers = await login_headers(client, "employee@demo.com")

    response = await client.put("/api/settings", headers=grantee_headers, json=DEFAULT_PAYLOAD)

    assert response.status_code == 200


async def test_non_admin_update_forbidden_and_unchanged(client, db):
    manager_headers = await login_headers(client, "manager@demo.com")
    employee_headers = await login_headers(client, "employee@demo.com")
    payload = {**DEFAULT_PAYLOAD, "work_start_time": "08:00"}

    manager_res = await client.put("/api/settings", headers=manager_headers, json=payload)
    employee_res = await client.put("/api/settings", headers=employee_headers, json=payload)

    assert manager_res.status_code == 403
    assert employee_res.status_code == 403
    row = await db.fetchrow("SELECT work_start_time FROM system_settings WHERE id = 1")
    assert str(row["work_start_time"]) == "09:00:00"


async def test_end_time_before_or_equal_start_time_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")
    payload = {**DEFAULT_PAYLOAD, "work_start_time": "18:00", "work_end_time": "18:00"}

    response = await client.put("/api/settings", headers=headers, json=payload)

    assert response.status_code == 400


async def test_grace_period_out_of_range_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")

    too_low = await client.put("/api/settings", headers=headers, json={**DEFAULT_PAYLOAD, "grace_period_minutes": -1})
    too_high = await client.put("/api/settings", headers=headers, json={**DEFAULT_PAYLOAD, "grace_period_minutes": 241})

    assert too_low.status_code == 400
    assert too_high.status_code == 400


async def test_bad_time_format_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.put("/api/settings", headers=headers, json={**DEFAULT_PAYLOAD, "work_start_time": "9:00"})

    assert response.status_code == 400


async def test_lunch_outside_work_hours_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")

    before_start = await client.put(
        "/api/settings", headers=headers, json={**DEFAULT_PAYLOAD, "lunch_start_time": "08:00"},
    )
    after_end = await client.put(
        "/api/settings", headers=headers, json={**DEFAULT_PAYLOAD, "lunch_end_time": "19:00"},
    )
    reversed_lunch = await client.put(
        "/api/settings", headers=headers,
        json={**DEFAULT_PAYLOAD, "lunch_start_time": "13:00", "lunch_end_time": "12:00"},
    )

    assert before_start.status_code == 400
    assert after_end.status_code == 400
    assert reversed_lunch.status_code == 400


async def test_admin_update_settings_persists_lunch_times(client):
    headers = await login_headers(client, "admin@demo.com")
    payload = {**DEFAULT_PAYLOAD, "lunch_start_time": "12:30", "lunch_end_time": "13:30"}

    await client.put("/api/settings", headers=headers, json=payload)
    response = await client.get("/api/settings", headers=headers)

    assert response.json()["settings"]["lunch_start_time"] == "12:30:00"
    assert response.json()["settings"]["lunch_end_time"] == "13:30:00"


async def test_system_settings_single_row_constraint(db):
    with pytest.raises(asyncpg.PostgresError):
        await db.execute(
            "INSERT INTO system_settings (id, work_start_time, work_end_time, lunch_start_time, lunch_end_time) "
            "VALUES (2, '09:00', '18:00', '12:00', '13:00')"
        )
    count = await db.fetchval("SELECT count(*) FROM system_settings")
    assert count == 1
