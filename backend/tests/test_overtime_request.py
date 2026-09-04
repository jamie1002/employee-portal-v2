"""加班申請：最短時數門檻、起算點防呆、待審申請阻擋（SPEC.md §4.4 §4.5）。"""

from app.utils.pg_types import pg_date
from app.utils.virtual_clock import set_virtual_clock
from tests.helpers import EMPLOYEE_ID, login_headers, taipei

TUESDAY = "2026-08-25"


async def test_half_hour_boundary_returns_201(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:00:00+08:00", "end_time": f"{TUESDAY}T18:30:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 201
    assert float(response.json()["request"]["hours"]) == 0.5


async def test_below_half_hour_rejected_with_dedicated_code(client):
    """12 分鐘捨去到 30 分鐘單位後為 0 小時，須擋下，不能顯示成 0 小時的申請。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:00:00+08:00", "end_time": f"{TUESDAY}T18:12:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OVERTIME_TOO_SHORT"


async def test_overtime_before_eligible_start_returns_400(client, db):
    """09:05 上班、18:15 下班（無請假）→ overtime_eligible_start = 18:35。18:20 申請應被擋下。"""
    headers = await login_headers(client, "employee@demo.com")

    await set_virtual_clock(taipei(2026, 8, 25, 9, 5))
    await client.post("/api/attendance/punch-in", headers=headers)
    await set_virtual_clock(taipei(2026, 8, 25, 18, 15))
    await client.post("/api/attendance/punch-out", headers=headers)

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:20:00+08:00", "end_time": f"{TUESDAY}T19:00:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OVERTIME_STARTS_TOO_EARLY"


async def test_overtime_at_or_after_eligible_start_succeeds(client):
    headers = await login_headers(client, "employee@demo.com")

    await set_virtual_clock(taipei(2026, 8, 25, 9, 5))
    await client.post("/api/attendance/punch-in", headers=headers)
    await set_virtual_clock(taipei(2026, 8, 25, 18, 15))
    await client.post("/api/attendance/punch-out", headers=headers)

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:35:00+08:00", "end_time": f"{TUESDAY}T19:30:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 201


async def test_overtime_blocked_by_pending_leave_request(client, db):
    await db.execute(
        """
        INSERT INTO leave_requests (user_id, leave_type, start_time, end_time, hours, reason, status)
        VALUES ($1, '事假', $2, $3, 3, '測試', 'pending')
        """,
        EMPLOYEE_ID, taipei(2026, 8, 25, 9, 0), taipei(2026, 8, 25, 12, 0),
    )
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T20:00:00+08:00", "end_time": f"{TUESDAY}T21:00:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PENDING_REQUEST_BLOCKS_OVERTIME"


async def test_overtime_blocked_by_pending_punch_request(client, db):
    await db.execute(
        """
        INSERT INTO punch_requests (user_id, target_date, type, requested_in_time, reason, status)
        VALUES ($1, $2, 'in', $3, '補打卡', 'pending')
        """,
        EMPLOYEE_ID, pg_date(TUESDAY), taipei(2026, 8, 25, 9, 0),
    )
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T20:00:00+08:00", "end_time": f"{TUESDAY}T21:00:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PENDING_REQUEST_BLOCKS_OVERTIME"


async def test_overtime_eligible_start_floored_on_non_workday(client):
    """假日出勤打卡帶秒數（08:56:37）時，非工作日的 eligible_start 若沒有截斷到分鐘，
    申請 08:56 開始的加班會被自己的防呆擋下（見 docs/PITFALLS.md B2）。"""
    saturday = "2026-08-29"
    headers = await login_headers(client, "employee@demo.com")

    await set_virtual_clock(taipei(2026, 8, 29, 8, 56, 37))
    await client.post("/api/attendance/punch-in", headers=headers)

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{saturday}T08:56:00+08:00", "end_time": f"{saturday}T10:56:00+08:00", "reason": "假日支援"},
    )

    assert response.status_code == 201


async def test_overtime_not_blocked_when_no_attendance_record(client):
    """完全沒有出勤紀錄的日子不擋（可能是主管補登，或該日尚未有任何紀錄）。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": "2026-08-26T20:00:00+08:00", "end_time": "2026-08-26T21:00:00+08:00", "reason": "支援"},
    )

    assert response.status_code == 201
