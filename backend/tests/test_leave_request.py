"""請假申請的建立與時數計算整合測試（SPEC.md §4.3 §4.5）。

純函式層級的時數計算已在 test_leave_hours.py 逐案例驗證；這裡測 API 這一層的
串接與驗證規則。虛擬時鐘只能撥到 2026-08-24（週一）~ 08-31（週一）之間，
剛好涵蓋一個完整週末，用來測跨週末請假。
"""

from app.utils.pg_types import pg_date
from tests.helpers import login_headers


async def test_create_success_returns_pending_with_computed_hours(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/leave-requests", headers=headers,
        json={
            "leave_type": "事假",
            "start_time": "2026-08-24T09:00:00+08:00",
            "end_time": "2026-08-24T18:00:00+08:00",
            "reason": "個人事務",
        },
    )

    assert response.status_code == 201
    body = response.json()["request"]
    assert body["status"] == "pending"
    assert float(body["hours"]) == 8.0


async def test_weekend_only_request_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/leave-requests", headers=headers,
        json={
            "leave_type": "事假",
            "start_time": "2026-08-29T09:00:00+08:00",  # 週六
            "end_time": "2026-08-30T18:00:00+08:00",  # 週日
            "reason": "個人事務",
        },
    )

    assert response.status_code == 400


async def test_end_before_start_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/leave-requests", headers=headers,
        json={
            "leave_type": "事假",
            "start_time": "2026-08-24T18:00:00+08:00",
            "end_time": "2026-08-24T09:00:00+08:00",
            "reason": "個人事務",
        },
    )

    assert response.status_code == 400


async def test_invalid_leave_type_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/leave-requests", headers=headers,
        json={
            "leave_type": "不存在的假別",
            "start_time": "2026-08-24T09:00:00+08:00",
            "end_time": "2026-08-24T18:00:00+08:00",
            "reason": "個人事務",
        },
    )

    assert response.status_code == 400


async def test_national_holiday_zero_hours_returns_400(client, db):
    await db.execute(
        "INSERT INTO holidays (holiday_date, name) VALUES ($1, '測試用展示視窗內假日') ON CONFLICT DO NOTHING",
        pg_date("2026-08-27"),
    )
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/leave-requests", headers=headers,
        json={
            "leave_type": "事假",
            "start_time": "2026-08-27T09:00:00+08:00",
            "end_time": "2026-08-27T18:00:00+08:00",
            "reason": "個人事務",
        },
    )

    assert response.status_code == 400


async def test_special_leave_reason_is_optional_others_required(client):
    headers = await login_headers(client, "employee@demo.com")

    special = await client.post(
        "/api/leave-requests", headers=headers,
        json={
            "leave_type": "特別休假",
            "start_time": "2026-08-24T09:00:00+08:00",
            "end_time": "2026-08-24T18:00:00+08:00",
            "reason": "",
        },
    )
    assert special.status_code == 201
    assert special.json()["request"]["reason"] == ""

    personal = await client.post(
        "/api/leave-requests", headers=headers,
        json={
            "leave_type": "事假",
            "start_time": "2026-08-25T09:00:00+08:00",
            "end_time": "2026-08-25T18:00:00+08:00",
            "reason": "",
        },
    )
    assert personal.status_code == 400


async def test_friday_to_monday_spans_weekend_and_totals_16_hours(client):
    """RUNBOOK 批 3 必測邊界：週五 09:00 → 週一 18:00，跨週末，時數應為 16.00
    （週六日不計入，不是把整個區間直接相減）。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/leave-requests", headers=headers,
        json={
            "leave_type": "特別休假",
            "start_time": "2026-08-28T09:00:00+08:00",  # 週五
            "end_time": "2026-08-31T18:00:00+08:00",  # 下週一
            "reason": "安排個人行程",
        },
    )

    assert response.status_code == 201
    assert float(response.json()["request"]["hours"]) == 16.0
    assert response.json()["request"]["status"] == "pending"


async def test_full_day_leave_approval_reflected_as_on_leave_without_raw_row(client):
    """整天請假核准後，生效狀態為 on_leave，即使 attendances 完全沒有對應的原始出勤列。"""
    from datetime import date

    from app.config.database import get_pool
    from app.services import attendance_effective

    employee_headers = await login_headers(client, "employee@demo.com")
    manager_headers = await login_headers(client, "manager@demo.com")

    create_res = await client.post(
        "/api/leave-requests", headers=employee_headers,
        json={
            "leave_type": "特別休假",
            "start_time": "2026-08-25T09:00:00+08:00",
            "end_time": "2026-08-25T18:00:00+08:00",
            "reason": "整天請假測試",
        },
    )
    request_id = create_res.json()["request"]["id"]

    review_res = await client.patch(
        f"/api/leave-requests/{request_id}/review", headers=manager_headers, json={"action": "approve"}
    )
    assert review_res.status_code == 200

    resolved = await attendance_effective.resolve_one(get_pool(), 3, date(2026, 8, 25))
    assert resolved["effective_status"] == "on_leave"
    assert float(resolved["effective_work_hours"]) == 8.0
    assert resolved["effective_punch_in_time"] is None
