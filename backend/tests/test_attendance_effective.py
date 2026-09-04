"""出勤生效值解析：已核准申請單於讀取時即時套用，不寫回 attendances（SPEC.md §4.2）。"""

from datetime import date

from app.utils.pg_types import pg_date
from app.utils.virtual_clock import set_virtual_clock
from tests.helpers import EMPLOYEE_ID, login_headers, taipei

MONDAY = date(2026, 8, 24)
TUESDAY = date(2026, 8, 25)


async def _insert_punch_request(db, user_id, target_date, *, status, requested_in=None, requested_out=None):
    await db.execute(
        """
        INSERT INTO punch_requests (
            user_id, target_date, type, requested_in_time, requested_out_time,
            reason, status, reviewer_id, reviewed_at, created_at
        )
        VALUES ($1, $2, $3, $4, $5, '測試用申請', $6, 1, now(), now())
        """,
        user_id,
        pg_date(target_date),
        "both" if requested_in and requested_out else ("in" if requested_in else "out"),
        requested_in,
        requested_out,
        status,
    )


async def _insert_leave_request(db, user_id, start_time, end_time, hours, *, status="approved"):
    await db.execute(
        """
        INSERT INTO leave_requests (
            user_id, leave_type, start_time, end_time, hours, reason,
            status, reviewer_id, reviewed_at, created_at
        )
        VALUES ($1, '事假', $2, $3, $4, '測試用請假', $5, 1, now(), now())
        """,
        user_id,
        start_time,
        end_time,
        hours,
        status,
    )


async def _my_records(client, headers):
    response = await client.get("/api/attendance/me", headers=headers)
    assert response.status_code == 200
    return response.json()["records"]


async def test_approved_punch_request_overrides_effective_values_without_touching_raw_row(client, db):
    """原始列仍是遲到的 09:30，生效值套用核准後的 09:00 並重新判定為正常。"""
    await set_virtual_clock(taipei(2026, 8, 24, 9, 30))
    headers = await login_headers(client, "employee@demo.com")
    await client.post("/api/attendance/punch-in", headers=headers)
    await _insert_punch_request(
        db, EMPLOYEE_ID, MONDAY, status="approved", requested_in=taipei(2026, 8, 24, 9, 0)
    )

    record = (await _my_records(client, headers))[0]

    assert record["status"] == "late"  # 原始事實不變
    assert record["effective_status"] == "normal"
    assert record["is_adjusted"] is True
    assert record["has_changes"] is True

    raw_status = await db.fetchval(
        "SELECT status FROM attendances WHERE user_id = $1 AND punch_date = $2",
        EMPLOYEE_ID,
        pg_date(MONDAY),
    )
    assert raw_status == "late"


async def test_pending_request_marks_has_changes_but_not_adjusted(client, db):
    """待審與已駁回的申請也要看得出「這天有動過」，但不算已異動。"""
    headers = await login_headers(client, "employee@demo.com")
    await client.post("/api/attendance/punch-in", headers=headers)
    await _insert_punch_request(
        db, EMPLOYEE_ID, MONDAY, status="pending", requested_in=taipei(2026, 8, 24, 9, 0)
    )

    record = (await _my_records(client, headers))[0]

    assert record["has_changes"] is True
    assert record["is_adjusted"] is False


async def test_full_day_leave_shows_as_on_leave_even_without_attendance_row(client, db):
    """整天請假的日子即使完全沒有出勤列，讀取時也要合成出一列。"""
    headers = await login_headers(client, "employee@demo.com")
    await _insert_leave_request(
        db, EMPLOYEE_ID, taipei(2026, 8, 25, 9, 0), taipei(2026, 8, 25, 18, 0), 8.0
    )

    records = await _my_records(client, headers)

    leave_day = next(row for row in records if row["punch_date"] == TUESDAY.isoformat())
    assert leave_day["effective_status"] == "on_leave"
    assert leave_day["effective_work_hours"] == "8.00"
    assert leave_day["is_adjusted"] is True


async def test_half_day_leave_shifts_expected_start_so_afternoon_arrival_is_normal(client, db):
    """上午請假到 12:00，下午 13:05 才到班不算遲到（應到班時間被推到午休結束）。"""
    headers = await login_headers(client, "employee@demo.com")
    await _insert_leave_request(
        db, EMPLOYEE_ID, taipei(2026, 8, 24, 9, 0), taipei(2026, 8, 24, 12, 0), 3.0
    )
    await set_virtual_clock(taipei(2026, 8, 24, 13, 5))
    await client.post("/api/attendance/punch-in", headers=headers)

    record = (await _my_records(client, headers))[0]

    assert record["effective_status"] == "normal"


async def test_missing_punch_out_is_flagged_only_for_past_days(client):
    headers = await login_headers(client, "employee@demo.com")
    await set_virtual_clock(taipei(2026, 8, 24, 9, 0))
    await client.post("/api/attendance/punch-in", headers=headers)

    today_record = (await _my_records(client, headers))[0]
    assert today_record["is_missing_punch_out"] is False  # 今天還沒下班很正常

    await set_virtual_clock(taipei(2026, 8, 25, 9, 0))
    past_record = next(
        row for row in await _my_records(client, headers) if row["punch_date"] == MONDAY.isoformat()
    )
    assert past_record["is_missing_punch_out"] is True


async def test_today_endpoint_reports_no_record_before_first_punch(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/attendance/today", headers=headers)

    attendance = response.json()["attendance"]
    assert attendance["has_punched_in"] is False
    assert attendance["punch_date"] == MONDAY.isoformat()
    assert attendance["is_workday"] is True


async def test_today_endpoint_returns_effective_values_after_punching(client):
    headers = await login_headers(client, "employee@demo.com")
    await client.post("/api/attendance/punch-in", headers=headers)

    response = await client.get("/api/attendance/today", headers=headers)

    attendance = response.json()["attendance"]
    assert attendance["has_punched_in"] is True
    assert attendance["effective_status"] == "normal"
