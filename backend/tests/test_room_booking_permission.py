"""場地預約的驗證規則與權限（SPEC.md §4.6 §6.4）。"""

from tests.helpers import EMPLOYEE_ID, login_headers

MONDAY = "2026-08-24"


async def test_booking_success_user_id_from_token(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "部門會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )

    assert response.status_code == 201
    assert response.json()["booking"]["user_id"] == EMPLOYEE_ID


async def test_smuggled_user_id_ignored(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "部門會議", "user_id": 1,
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )

    assert response.status_code == 201
    assert response.json()["booking"]["user_id"] == EMPLOYEE_ID


async def test_missing_required_field_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={"room_id": 1, "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00"},
    )

    assert response.status_code == 400


async def test_end_before_start_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "部門會議",
            "start_time": f"{MONDAY}T10:00:00+08:00", "end_time": f"{MONDAY}T09:00:00+08:00",
        },
    )

    assert response.status_code == 400


async def test_cross_day_booking_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "跨日",
            "start_time": f"{MONDAY}T23:00:00+08:00", "end_time": "2026-08-25T01:00:00+08:00",
        },
    )

    assert response.status_code == 400


async def test_nonexistent_room_returns_404(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 999, "title": "部門會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )

    assert response.status_code == 404


async def test_list_by_date_includes_room_and_booker_names(client):
    headers = await login_headers(client, "employee@demo.com")
    await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "部門會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )

    response = await client.get(f"/api/room-bookings?date={MONDAY}", headers=headers)

    assert response.status_code == 200
    booking = response.json()["bookings"][0]
    assert booking["room_name"] == "會議室 A"
    assert booking["booked_by_name"] == "陳小華"


async def test_filter_excludes_cancelled_by_default(client):
    headers = await login_headers(client, "employee@demo.com")
    create_res = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "部門會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )
    booking_id = create_res.json()["booking"]["id"]
    await client.patch(f"/api/room-bookings/{booking_id}/cancel", headers=headers)

    response = await client.get(f"/api/room-bookings?date={MONDAY}&room_id=1", headers=headers)

    assert response.json()["bookings"] == []


async def test_no_data_returns_empty_array(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get(f"/api/room-bookings?date={MONDAY}", headers=headers)

    assert response.status_code == 200
    assert response.json()["bookings"] == []


async def test_owner_can_cancel_own_booking(client):
    headers = await login_headers(client, "employee@demo.com")
    create_res = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "部門會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )
    booking_id = create_res.json()["booking"]["id"]

    response = await client.patch(f"/api/room-bookings/{booking_id}/cancel", headers=headers)

    assert response.status_code == 200
    assert response.json()["booking"]["status"] == "cancelled"


async def test_employee_cancel_others_booking_forbidden(client, db):
    employee_headers = await login_headers(client, "employee@demo.com")
    manager_headers = await login_headers(client, "manager@demo.com")
    create_res = await client.post(
        "/api/room-bookings", headers=manager_headers,
        json={
            "room_id": 1, "title": "主管的會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )
    booking_id = create_res.json()["booking"]["id"]

    response = await client.patch(f"/api/room-bookings/{booking_id}/cancel", headers=employee_headers)

    assert response.status_code == 403
    row = await db.fetchrow("SELECT status FROM room_bookings WHERE id = $1", booking_id)
    assert row["status"] == "confirmed"


async def test_admin_cancel_others_booking_ok(client):
    admin_headers = await login_headers(client, "admin@demo.com")
    employee_headers = await login_headers(client, "employee@demo.com")
    create_res = await client.post(
        "/api/room-bookings", headers=employee_headers,
        json={
            "room_id": 1, "title": "員工的會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )
    booking_id = create_res.json()["booking"]["id"]

    response = await client.patch(f"/api/room-bookings/{booking_id}/cancel", headers=admin_headers)

    assert response.status_code == 200


async def test_admin_delete_ok_non_admin_forbidden(client, db):
    admin_headers = await login_headers(client, "admin@demo.com")
    employee_headers = await login_headers(client, "employee@demo.com")
    create_res = await client.post(
        "/api/room-bookings", headers=employee_headers,
        json={
            "room_id": 1, "title": "員工的會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )
    booking_id = create_res.json()["booking"]["id"]

    forbidden = await client.delete(f"/api/room-bookings/{booking_id}", headers=employee_headers)
    assert forbidden.status_code == 403

    response = await client.delete(f"/api/room-bookings/{booking_id}", headers=admin_headers)
    assert response.status_code == 200
    row = await db.fetchrow("SELECT id FROM room_bookings WHERE id = $1", booking_id)
    assert row is None


async def test_cancel_then_rebook_same_slot(client):
    employee_headers = await login_headers(client, "employee@demo.com")
    manager_headers = await login_headers(client, "manager@demo.com")
    create_res = await client.post(
        "/api/room-bookings", headers=employee_headers,
        json={
            "room_id": 1, "title": "員工的會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )
    booking_id = create_res.json()["booking"]["id"]
    await client.patch(f"/api/room-bookings/{booking_id}/cancel", headers=employee_headers)

    response = await client.post(
        "/api/room-bookings", headers=manager_headers,
        json={
            "room_id": 1, "title": "主管的會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )

    assert response.status_code == 201


async def test_double_cancel_conflict_and_missing_id(client):
    headers = await login_headers(client, "employee@demo.com")
    create_res = await client.post(
        "/api/room-bookings", headers=headers,
        json={
            "room_id": 1, "title": "部門會議",
            "start_time": f"{MONDAY}T09:00:00+08:00", "end_time": f"{MONDAY}T10:00:00+08:00",
        },
    )
    booking_id = create_res.json()["booking"]["id"]
    await client.patch(f"/api/room-bookings/{booking_id}/cancel", headers=headers)

    duplicate = await client.patch(f"/api/room-bookings/{booking_id}/cancel", headers=headers)
    assert duplicate.status_code == 409

    missing = await client.patch("/api/room-bookings/999999/cancel", headers=headers)
    assert missing.status_code == 404
