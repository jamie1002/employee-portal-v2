"""補打卡申請的建立、防重複、未來日期防呆（SPEC.md §4.5）。"""

from app.utils.virtual_clock import set_virtual_clock
from tests.helpers import EMPLOYEE_ID, login_headers, taipei

MONDAY = "2026-08-24"


async def test_type_in_create_success(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/punch-requests",
        headers=headers,
        json={"type": "in", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:00:00+08:00", "reason": "忘記打卡"},
    )

    assert response.status_code == 201
    body = response.json()["request"]
    assert body["status"] == "pending"
    assert body["user_id"] == EMPLOYEE_ID


async def test_type_in_missing_requested_in_time_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/punch-requests", headers=headers,
        json={"type": "in", "target_date": MONDAY, "reason": "忘記打卡"},
    )

    assert response.status_code == 400


async def test_type_both_missing_one_side_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/punch-requests", headers=headers,
        json={"type": "both", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:00:00+08:00", "reason": "忘記打卡"},
    )

    assert response.status_code == 400


async def test_type_both_out_before_in_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/punch-requests", headers=headers,
        json={
            "type": "both", "target_date": MONDAY,
            "requested_in_time": f"{MONDAY}T18:00:00+08:00",
            "requested_out_time": f"{MONDAY}T09:00:00+08:00",
            "reason": "忘記打卡",
        },
    )

    assert response.status_code == 400


async def test_missing_reason_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/punch-requests", headers=headers,
        json={"type": "in", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:00:00+08:00"},
    )

    assert response.status_code == 400


async def test_future_target_date_returns_400(client):
    """不得為未來日期，判斷基準是虛擬時鐘的營業日，不是真實系統時間。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/punch-requests", headers=headers,
        json={"type": "in", "target_date": "2026-08-25", "requested_in_time": "2026-08-25T09:00:00+08:00", "reason": "忘記打卡"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_smuggled_user_id_is_ignored(client, db):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/punch-requests", headers=headers,
        json={
            "type": "in", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:00:00+08:00",
            "reason": "忘記打卡", "user_id": 1,
        },
    )

    assert response.status_code == 201
    assert response.json()["request"]["user_id"] == EMPLOYEE_ID


async def test_duplicate_pending_same_day_different_type_returns_409(client):
    headers = await login_headers(client, "employee@demo.com")
    await client.post(
        "/api/punch-requests", headers=headers,
        json={
            "type": "both", "target_date": MONDAY,
            "requested_in_time": f"{MONDAY}T09:00:00+08:00",
            "requested_out_time": f"{MONDAY}T18:00:00+08:00",
            "reason": "不上下班卡",
        },
    )

    response = await client.post(
        "/api/punch-requests", headers=headers,
        json={"type": "in", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:05:00+08:00", "reason": "又想補上班卡"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_PUNCH_REQUEST"


async def test_resubmit_after_rejection_allowed(client):
    employee_headers = await login_headers(client, "employee@demo.com")
    manager_headers = await login_headers(client, "manager@demo.com")

    create_res = await client.post(
        "/api/punch-requests", headers=employee_headers,
        json={"type": "in", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:00:00+08:00", "reason": "忘記打卡"},
    )
    await client.patch(
        f"/api/punch-requests/{create_res.json()['request']['id']}/review",
        headers=manager_headers, json={"action": "reject", "review_note": "證據不足"},
    )

    response = await client.post(
        "/api/punch-requests", headers=employee_headers,
        json={"type": "in", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:00:00+08:00", "reason": "補齊證據重新申請"},
    )

    assert response.status_code == 201


async def test_my_requests_only_own_ignores_other_user_id_param(client):
    headers = await login_headers(client, "employee@demo.com")
    await client.post(
        "/api/punch-requests", headers=headers,
        json={"type": "in", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:00:00+08:00", "reason": "忘記打卡"},
    )

    response = await client.get("/api/punch-requests/me?user_id=1", headers=headers)

    assert response.status_code == 200
    assert all(row["user_id"] == EMPLOYEE_ID for row in response.json()["requests"])


async def test_status_filter_and_reviewed_fields(client):
    employee_headers = await login_headers(client, "employee@demo.com")
    manager_headers = await login_headers(client, "manager@demo.com")

    create_res = await client.post(
        "/api/punch-requests", headers=employee_headers,
        json={"type": "in", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:00:00+08:00", "reason": "忘記打卡"},
    )
    request_id = create_res.json()["request"]["id"]
    await client.patch(
        f"/api/punch-requests/{request_id}/review", headers=manager_headers,
        json={"action": "reject", "review_note": "證明文件不足"},
    )

    pending = await client.get("/api/punch-requests/me?status=pending", headers=employee_headers)
    assert pending.json()["requests"] == []

    rejected = await client.get("/api/punch-requests/me?status=rejected", headers=employee_headers)
    assert len(rejected.json()["requests"]) == 1
    assert rejected.json()["requests"][0]["reviewer_name"] == "王小明"
    assert rejected.json()["requests"][0]["reviewed_at"]
    assert rejected.json()["requests"][0]["review_note"] == "證明文件不足"


async def test_approved_punch_request_is_reflected_in_effective_attendance(client):
    """核准後原始出勤列不受影響，生效值改讀申請單的值（SPEC.md §4.2）。"""
    from app.services import attendance_effective

    employee_headers = await login_headers(client, "employee@demo.com")
    manager_headers = await login_headers(client, "manager@demo.com")

    await set_virtual_clock(taipei(2026, 8, 24, 9, 30))
    await client.post("/api/attendance/punch-in", headers=employee_headers)

    create_res = await client.post(
        "/api/punch-requests", headers=employee_headers,
        json={"type": "in", "target_date": MONDAY, "requested_in_time": f"{MONDAY}T09:00:00+08:00", "reason": "補正打卡時間"},
    )
    review_res = await client.patch(
        f"/api/punch-requests/{create_res.json()['request']['id']}/review",
        headers=manager_headers, json={"action": "approve"},
    )
    assert review_res.status_code == 200

    from app.config.database import get_pool
    from datetime import date

    resolved = await attendance_effective.resolve_one(get_pool(), EMPLOYEE_ID, date(2026, 8, 24))
    assert resolved["effective_status"] == "normal"  # 原本 09:30 是遲到，核准後改為正常
    assert resolved["is_adjusted"] is True
