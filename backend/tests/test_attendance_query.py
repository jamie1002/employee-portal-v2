"""出勤查詢：分頁、狀態篩選語意、範圍限縮。"""

from datetime import date, timedelta

from app.utils.pg_types import pg_date
from tests.helpers import EMPLOYEE_ID, OTHER_EMPLOYEE_ID, login_headers, taipei

WEDNESDAY = date(2026, 8, 19)  # 正常
THURSDAY = date(2026, 8, 20)   # 早退
FRIDAY = date(2026, 8, 21)     # 未打下班卡


async def _insert_attendance(db, user_id, day, punch_in=None, punch_out=None, status="normal"):
    await db.execute(
        """
        INSERT INTO attendances (
            user_id, punch_date, punch_in_time, punch_out_time, status, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, now(), now())
        ON CONFLICT (user_id, punch_date) DO NOTHING
        """,
        user_id,
        pg_date(day),
        punch_in,
        punch_out,
        status,
    )


async def _seed_three_status_days(db):
    await _insert_attendance(
        db, EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0), taipei(2026, 8, 19, 18, 0)
    )
    await _insert_attendance(
        db, EMPLOYEE_ID, THURSDAY, taipei(2026, 8, 20, 9, 0), taipei(2026, 8, 20, 17, 0)
    )
    await _insert_attendance(db, EMPLOYEE_ID, FRIDAY, taipei(2026, 8, 21, 9, 0))


async def test_my_records_are_paginated(client, db):
    for offset in range(25):
        day = date(2026, 7, 1) + timedelta(days=offset)
        await _insert_attendance(db, EMPLOYEE_ID, day, taipei(2026, 7, 1, 9, 0))
    headers = await login_headers(client, "employee@demo.com")

    first_page = await client.get("/api/attendance/me?page=1&page_size=10", headers=headers)

    body = first_page.json()
    assert body["total"] == 25
    assert body["page_size"] == 10
    assert len(body["records"]) == 10

    last_page = await client.get("/api/attendance/me?page=3&page_size=10", headers=headers)
    assert len(last_page.json()["records"]) == 5


async def test_page_size_over_limit_is_rejected(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/attendance/me?page_size=101", headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_invalid_status_filter_is_rejected(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/attendance/me?status=not_a_status", headers=headers)

    assert response.status_code == 400


async def test_normal_filter_excludes_early_leave_and_missing_punch_out(client, db):
    """篩「正常」不該把早退／未打下班卡的日子一併篩出——那些日子的 effective_status
    確實仍是 normal，但畫面上會同時掛「早退」徽章，說它正常就自相矛盾。"""
    await _seed_three_status_days(db)
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/attendance/me?status=normal", headers=headers)

    dates = [row["punch_date"] for row in response.json()["records"]]
    assert dates == [WEDNESDAY.isoformat()]


async def test_early_leave_filter_matches_derived_flag(client, db):
    await _seed_three_status_days(db)
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/attendance/me?status=early_leave", headers=headers)

    dates = [row["punch_date"] for row in response.json()["records"]]
    assert dates == [THURSDAY.isoformat()]


async def test_missing_punch_out_filter_matches_derived_flag(client, db):
    await _seed_three_status_days(db)
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/attendance/me?status=missing_punch_out", headers=headers)

    dates = [row["punch_date"] for row in response.json()["records"]]
    assert dates == [FRIDAY.isoformat()]


async def test_date_range_filter_limits_results(client, db):
    await _seed_three_status_days(db)
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get(
        "/api/attendance/me?start_date=2026-08-20&end_date=2026-08-20", headers=headers
    )

    dates = [row["punch_date"] for row in response.json()["records"]]
    assert dates == [THURSDAY.isoformat()]


async def test_company_attendance_is_admin_only(client):
    employee_headers = await login_headers(client, "employee@demo.com")
    manager_headers = await login_headers(client, "manager@demo.com")

    assert (await client.get("/api/attendance", headers=employee_headers)).status_code == 403
    assert (await client.get("/api/attendance", headers=manager_headers)).status_code == 403


async def test_company_attendance_can_filter_by_department(client, db):
    await _insert_attendance(db, EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0))
    await _insert_attendance(db, OTHER_EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0))
    headers = await login_headers(client, "admin@demo.com")

    all_records = await client.get("/api/attendance?start_date=2026-08-19&end_date=2026-08-19", headers=headers)
    assert len(all_records.json()["records"]) == 2

    filtered = await client.get(
        "/api/attendance?department_id=1&start_date=2026-08-19&end_date=2026-08-19", headers=headers
    )
    user_ids = {row["user_id"] for row in filtered.json()["records"]}
    assert user_ids == {EMPLOYEE_ID}


async def test_changes_requires_a_date_range(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/attendance/changes", headers=headers)

    assert response.status_code == 400


async def test_employee_changes_query_ignores_smuggled_user_id(client, db):
    """一般員工的查詢對象一律取自 token，帶了別人的 user_id 也只會拿到自己的。"""
    await db.execute(
        """
        INSERT INTO punch_requests (user_id, target_date, type, requested_in_time, reason, status, created_at)
        VALUES ($1, $2, 'in', $3, '別人的申請', 'pending', now())
        """,
        OTHER_EMPLOYEE_ID,
        pg_date(WEDNESDAY),
        taipei(2026, 8, 19, 9, 0),
    )
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get(
        f"/api/attendance/changes?start_date=2026-08-19&end_date=2026-08-19&user_id={OTHER_EMPLOYEE_ID}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["changes"] == []


async def test_manager_cannot_query_changes_of_another_department(client):
    headers = await login_headers(client, "manager@demo.com")  # 研發部

    response = await client.get(
        f"/api/attendance/changes?start_date=2026-08-19&end_date=2026-08-19&user_id={OTHER_EMPLOYEE_ID}",
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_manager_can_query_changes_of_own_department(client, db):
    await db.execute(
        """
        INSERT INTO punch_requests (user_id, target_date, type, requested_in_time, reason, status, created_at)
        VALUES ($1, $2, 'in', $3, '同部門的申請', 'pending', now())
        """,
        EMPLOYEE_ID,
        pg_date(WEDNESDAY),
        taipei(2026, 8, 19, 9, 0),
    )
    headers = await login_headers(client, "manager@demo.com")

    response = await client.get(
        f"/api/attendance/changes?start_date=2026-08-19&end_date=2026-08-19&user_id={EMPLOYEE_ID}",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()["changes"]) == 1


async def test_admin_can_query_changes_across_departments(client, db):
    await db.execute(
        """
        INSERT INTO punch_requests (user_id, target_date, type, requested_in_time, reason, status, created_at)
        VALUES ($1, $2, 'in', $3, '跨部門申請', 'pending', now())
        """,
        OTHER_EMPLOYEE_ID,
        pg_date(WEDNESDAY),
        taipei(2026, 8, 19, 9, 0),
    )
    headers = await login_headers(client, "admin@demo.com")

    response = await client.get(
        "/api/attendance/changes?start_date=2026-08-19&end_date=2026-08-19", headers=headers
    )

    assert response.status_code == 200
    assert len(response.json()["changes"]) == 1
