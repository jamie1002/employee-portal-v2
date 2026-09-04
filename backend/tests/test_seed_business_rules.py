"""種子業務資料的自洽性驗證（docs/PITFALLS.md E1）。

**全表掃描**，不是抽查特定幾筆——前一版曾經兩次讓種子資料自己過不了系統剛加上
的防呆（示範加班申請的起始時間早於系統算出的最早可申請時間），根因是沒有任何
測試在驗證種子資料是否通過業務規則，等使用者手動實測才發現。
"""

import pytest_asyncio

from app.config.settings import app_settings
from app.db_scripts.seed import apply_demo_seed
from app.services.attendance_effective import resolve_one
from app.services.leave_hours import calculate_leave_hours, calculate_overtime_hours
from app.services.work_hours import (
    WorkSettings,
    calculate_work_hours,
    compute_expected_start,
    compute_overtime_eligible_start,
    judge_status,
)
from app.utils.timezone import get_business_date

_TZ = app_settings.APP_TIMEZONE
_REQUEST_TABLES = ("punch_requests", "leave_requests", "overtime_requests")


@pytest_asyncio.fixture(autouse=True)
async def _demo_seeded(db):
    """這個檔案專屬：疊加示範用業務資料（見 app/db_scripts/seed_business_data.py）。
    其他測試檔沿用的每測試重置 fixture 只還原靜態參考資料，業務資料表刻意
    保持乾淨（見 app/db_scripts/seed.py 模組說明）。"""
    await apply_demo_seed(db)


async def _work_settings(db) -> WorkSettings:
    row = await db.fetchrow(
        "SELECT work_start_time, work_end_time, lunch_start_time, lunch_end_time, grace_period_minutes "
        "FROM system_settings WHERE id = 1"
    )
    return WorkSettings.from_row(row)


async def test_all_attendance_rows_match_recomputed_status_and_hours(db):
    settings = await _work_settings(db)
    rows = await db.fetch(
        "SELECT user_id, punch_date, punch_in_time, punch_out_time, status, work_hours "
        "FROM attendances WHERE punch_in_time IS NOT NULL"
    )
    assert len(rows) > 0, "種子資料應該至少有幾筆有打卡的出勤列可供比對"

    for row in rows:
        expected_start = compute_expected_start(row["punch_date"], settings, _TZ)
        expected_status = judge_status(row["punch_in_time"], row["punch_date"], settings, _TZ, expected_start)
        expected_hours = calculate_work_hours(
            row["punch_in_time"], row["punch_out_time"], row["punch_date"], settings, _TZ,
            workday=True, expected_start=expected_start,
        )

        label = f"user_id={row['user_id']} punch_date={row['punch_date']}"
        assert row["status"] == expected_status, label
        if expected_hours is None:
            assert row["work_hours"] is None, label
        else:
            assert float(row["work_hours"]) == expected_hours, label


async def test_all_leave_requests_hours_match_recomputed_value(db):
    settings = await _work_settings(db)
    rows = await db.fetch("SELECT id, start_time, end_time, hours FROM leave_requests")
    assert len(rows) > 0

    for row in rows:
        expected = calculate_leave_hours(row["start_time"], row["end_time"], settings, _TZ)
        assert float(row["hours"]) == expected, f"leave_request id={row['id']}"


async def test_all_overtime_requests_hours_match_recomputed_value(db):
    settings = await _work_settings(db)
    rows = await db.fetch("SELECT id, start_time, end_time, hours FROM overtime_requests")
    assert len(rows) > 0

    for row in rows:
        expected = calculate_overtime_hours(row["start_time"], row["end_time"], settings, _TZ)
        assert float(row["hours"]) == expected, f"overtime_request id={row['id']}"


async def test_all_overtime_requests_start_at_or_after_eligible_start(pool, db):
    """docs/PITFALLS.md E1 的原始事故：示範加班申請的起始時間早於系統算出的
    最早可申請時間。這裡逐筆重算，不是只挑一筆。"""
    settings = await _work_settings(db)
    rows = await db.fetch("SELECT id, user_id, start_time FROM overtime_requests")
    assert len(rows) > 0

    for row in rows:
        punch_date = get_business_date(row["start_time"], _TZ)
        effective = await resolve_one(pool, row["user_id"], punch_date)
        if not effective or not effective["effective_punch_in_time"]:
            continue
        eligible_start = compute_overtime_eligible_start(
            effective["effective_punch_in_time"], punch_date, settings, _TZ,
        )
        assert row["start_time"] >= eligible_start, f"overtime_request id={row['id']}"


async def test_all_reviewed_requests_have_reviewer_and_created_before_reviewed(db):
    checked_any = False
    for table in _REQUEST_TABLES:
        rows = await db.fetch(f"SELECT id, created_at, reviewed_at, reviewer_id FROM {table} WHERE status <> 'pending'")
        for row in rows:
            checked_any = True
            label = f"{table} id={row['id']}"
            assert row["reviewer_id"] is not None, label
            assert row["reviewed_at"] is not None, label
            assert row["created_at"] < row["reviewed_at"], label
    assert checked_any, "種子資料應該至少有幾筆已審核的申請單可供比對"


async def test_pending_requests_have_no_reviewer(db):
    checked_any = False
    for table in _REQUEST_TABLES:
        rows = await db.fetch(f"SELECT id, reviewer_id, reviewed_at FROM {table} WHERE status = 'pending'")
        for row in rows:
            checked_any = True
            label = f"{table} id={row['id']}"
            assert row["reviewer_id"] is None, label
            assert row["reviewed_at"] is None, label
    assert checked_any, "種子資料應該至少有幾筆待審申請單可供比對"
