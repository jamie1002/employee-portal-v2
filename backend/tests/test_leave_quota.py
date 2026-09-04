"""假別配額計算（SPEC.md §4.3.1）：特別休假到職週年制、其餘假別曆年制。"""

from datetime import date

from app.services.leave_quota import current_special_leave_period, special_leave_days
from tests.helpers import login_headers


def test_special_leave_days_table():
    assert special_leave_days(0) == 0
    assert special_leave_days(5) == 0
    assert special_leave_days(6) == 3
    assert special_leave_days(11) == 3
    assert special_leave_days(12) == 7
    assert special_leave_days(24) == 10
    assert special_leave_days(36) == 14
    assert special_leave_days(48) == 14
    assert special_leave_days(60) == 15
    assert special_leave_days(108) == 15
    assert special_leave_days(120) == 15  # 滿 10 年整仍是 15，第 11 年起才開始 +1
    assert special_leave_days(132) == 16  # 滿 11 年
    assert special_leave_days(120 + 12 * 15) == 30  # 上限 30 天
    assert special_leave_days(120 + 12 * 20) == 30


def test_current_special_leave_period_before_six_months():
    period = current_special_leave_period(date(2026, 6, 1), date(2026, 8, 24))
    assert period.days == 0
    assert period.period_start == date(2026, 6, 1)
    assert period.period_end == date(2026, 12, 1)


def test_current_special_leave_period_between_six_and_twelve_months():
    period = current_special_leave_period(date(2026, 1, 1), date(2026, 8, 24))
    assert period.days == 3
    assert period.period_start == date(2026, 7, 1)
    assert period.period_end == date(2027, 1, 1)


def test_current_special_leave_period_month_end_clamped():
    """1/31 到職，加 6 個月不是溢位成 8/3，而是夾在 7/31。"""
    period = current_special_leave_period(date(2026, 1, 31), date(2026, 8, 24))
    assert period.period_start == date(2026, 7, 31)


async def test_my_quota_endpoint_returns_four_leave_types(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/leave-quota/me", headers=headers)

    assert response.status_code == 200
    leave_types = {row["leave_type"] for row in response.json()["quota"]}
    assert leave_types == {"特別休假", "事假", "病假", "公假"}


async def test_personal_leave_quota_is_14_days_in_hours(client, db):
    """陳小華（employee@demo.com）2025-09-01 到職，事假曆年制配額固定 14 天，
    換算成小時＝ 14 × 8 = 112（表定工時 8 小時／日）。"""
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/leave-quota/me", headers=headers)

    personal = next(row for row in response.json()["quota"] if row["leave_type"] == "事假")
    assert personal["quota_hours"] == 112.0
    assert personal["used_hours"] == 0.0


async def test_public_leave_has_no_quota_cap(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/leave-quota/me", headers=headers)

    public_leave = next(row for row in response.json()["quota"] if row["leave_type"] == "公假")
    assert public_leave["quota_hours"] is None
    assert public_leave["remaining_hours"] is None


async def test_approved_leave_reduces_remaining_quota(client):
    employee_headers = await login_headers(client, "employee@demo.com")
    manager_headers = await login_headers(client, "manager@demo.com")

    create_res = await client.post(
        "/api/leave-requests", headers=employee_headers,
        json={
            "leave_type": "事假",
            "start_time": "2026-08-24T09:00:00+08:00",
            "end_time": "2026-08-24T18:00:00+08:00",
            "reason": "個人事務",
        },
    )
    await client.patch(
        f"/api/leave-requests/{create_res.json()['request']['id']}/review",
        headers=manager_headers, json={"action": "approve"},
    )

    response = await client.get("/api/leave-quota/me", headers=employee_headers)

    personal = next(row for row in response.json()["quota"] if row["leave_type"] == "事假")
    assert personal["used_hours"] == 8.0
    assert personal["remaining_hours"] == 104.0


async def test_pending_leave_does_not_reduce_quota(client):
    """待審請假不影響配額，只有已核准才計入已用時數。"""
    headers = await login_headers(client, "employee@demo.com")
    await client.post(
        "/api/leave-requests", headers=headers,
        json={
            "leave_type": "事假",
            "start_time": "2026-08-24T09:00:00+08:00",
            "end_time": "2026-08-24T18:00:00+08:00",
            "reason": "個人事務",
        },
    )

    response = await client.get("/api/leave-quota/me", headers=headers)

    personal = next(row for row in response.json()["quota"] if row["leave_type"] == "事假")
    assert personal["used_hours"] == 0.0
