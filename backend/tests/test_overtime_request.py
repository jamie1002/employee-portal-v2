"""加班申請：最短時數門檻、起算點防呆、待審申請阻擋（SPEC.md §4.4 §4.5）。"""

from app.utils.pg_types import pg_date
from app.utils.virtual_clock import set_virtual_clock
from tests.helpers import EMPLOYEE_ID, login_headers, taipei

TUESDAY = "2026-08-25"
SATURDAY = "2026-08-29"


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


async def test_create_success(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:00:00+08:00", "end_time": f"{TUESDAY}T20:00:00+08:00", "reason": "專案上線前準備"},
    )

    assert response.status_code == 201
    assert float(response.json()["request"]["hours"]) == 2
    assert response.json()["request"]["status"] == "pending"


async def test_hours_not_excluded_on_weekend(client):
    # 區間刻意選在午休之後（13:00–17:00），避免與午休扣除規則混在一起。
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{SATURDAY}T13:00:00+08:00", "end_time": f"{SATURDAY}T17:00:00+08:00", "reason": "假日支援上線"},
    )

    assert response.status_code == 201
    assert float(response.json()["request"]["hours"]) == 4


async def test_hours_deduct_lunch_overlap_across_workday_lunch(client):
    """假日出勤橫跨表定午休的加班申請，午休時段不應計入加班時數——
    09:00–13:00 扣除 12:00–13:00 的午休重疊，剩 3 小時。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{SATURDAY}T09:00:00+08:00", "end_time": f"{SATURDAY}T13:00:00+08:00", "reason": "假日支援上線"},
    )

    assert response.status_code == 201
    assert float(response.json()["request"]["hours"]) == 3


async def test_end_before_start_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T20:00:00+08:00", "end_time": f"{TUESDAY}T18:00:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 400


async def test_start_not_half_hour_aligned_hours_floored(client):
    """不鎖死起訖時間須對齊整點／半點——18:15~20:00 共 1h45m，
    以 30 分鐘為單位捨去為 1.5 小時，應成功送出。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:15:00+08:00", "end_time": f"{TUESDAY}T20:00:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 201
    assert float(response.json()["request"]["hours"]) == 1.5


async def test_end_not_half_hour_aligned_hours_floored(client):
    """18:00~20:45 共 2h45m，以 30 分鐘為單位捨去為 2.5 小時。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:00:00+08:00", "end_time": f"{TUESDAY}T20:45:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 201
    assert float(response.json()["request"]["hours"]) == 2.5


async def test_user_reported_example_18_40_to_21_10_is_2_5_hours(client):
    """迴歸鎖定：18:40 加班到 21:10 應為完整 2.5 小時，不能因為整點／半點
    對齊規則被誤判成其他時數或直接擋下。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:40:00+08:00", "end_time": f"{TUESDAY}T21:10:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 201
    assert float(response.json()["request"]["hours"]) == 2.5


async def test_half_hour_boundary_ok(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:30:00+08:00", "end_time": f"{TUESDAY}T20:30:00+08:00", "reason": "加班"},
    )

    assert response.status_code == 201
    assert float(response.json()["request"]["hours"]) == 2


async def test_missing_reason_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/overtime-requests", headers=headers,
        json={"start_time": f"{TUESDAY}T18:00:00+08:00", "end_time": f"{TUESDAY}T20:00:00+08:00"},
    )

    assert response.status_code == 400
