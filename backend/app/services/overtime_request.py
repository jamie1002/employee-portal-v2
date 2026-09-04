"""加班申請的業務邏輯（SPEC.md §4.4 §4.5）。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import asyncpg

from app.config.settings import app_settings
from app.repositories import (
    leave_request_repository,
    overtime_request_repository,
    punch_request_repository,
    settings_repository,
)
from app.services import attendance_effective
from app.services.leave_hours import calculate_overtime_hours, compute_leave_hours_for_date
from app.services.work_hours import WorkSettings, compute_expected_start, compute_overtime_eligible_start
from app.services.workday import is_workday
from app.utils.errors import AppError
from app.utils.timezone import get_business_date


def _format_taipei(moment: datetime, tz: str) -> str:
    local = moment.astimezone(ZoneInfo(tz))
    return f"{local.month:02d}/{local.day:02d} {local.hour:02d}:{local.minute:02d}"


async def _has_pending_request_covering(pool: asyncpg.Pool, user_id: int, punch_date, tz: str) -> bool:
    """當天若有待審核的請假或補打卡申請，代表正常工時尚未確定，必須先完成審核
    才能申請加班（SPEC.md §4.4：先確認正常工時沒問題才能算加班）。"""
    if await punch_request_repository.exists_pending_for_date(pool, user_id, punch_date):
        return True
    return await leave_request_repository.exists_pending_covering_date(pool, user_id, punch_date, tz)


async def create(
    pool: asyncpg.Pool, user_id: int, start_time: datetime, end_time: datetime, reason: str, created_at: datetime
) -> dict:
    tz = app_settings.APP_TIMEZONE
    settings = WorkSettings.from_row(await settings_repository.get_settings(pool))

    hours = calculate_overtime_hours(start_time, end_time, settings, tz)
    if hours <= 0:
        raise AppError(400, "加班時數不得少於 0.5 小時（30 分鐘）。", "OVERTIME_TOO_SHORT")

    punch_date = get_business_date(start_time, tz=tz)

    if await _has_pending_request_covering(pool, user_id, punch_date, tz):
        raise AppError(
            400, "當天有待審核的請假或補打卡申請，請先完成審核再申請加班。", "PENDING_REQUEST_BLOCKS_OVERTIME"
        )

    # 以生效出勤（見 attendance_effective.py）算出當天最早可認列加班的時間點；
    # 完全沒有出勤紀錄的日子不擋（可能是主管補登、或該日尚未有任何紀錄）。
    resolved = await attendance_effective.resolve_one(pool, user_id, punch_date)
    if resolved and resolved["effective_punch_in_time"]:
        workday = await is_workday(pool, punch_date)
        expected_start = None
        leave_hours = 0.0
        if workday:
            leave_intervals = await leave_request_repository.find_approved_intervals_for_date(
                pool, user_id, punch_date, tz
            )
            expected_start = compute_expected_start(punch_date, settings, tz, leave_intervals)
            leave_hours = compute_leave_hours_for_date(punch_date, leave_intervals, settings, tz)

        eligible_start = compute_overtime_eligible_start(
            resolved["effective_punch_in_time"], punch_date, settings, tz, workday,
            expected_start=expected_start, leave_hours=leave_hours,
        )
        if start_time < eligible_start:
            raise AppError(
                400,
                f"加班最早可從 {_format_taipei(eligible_start, tz)} 開始申請。",
                "OVERTIME_STARTS_TOO_EARLY",
            )

    request = await overtime_request_repository.create(pool, user_id, start_time, end_time, hours, reason, created_at)
    return dict(request)


async def get_my_requests(pool: asyncpg.Pool, user_id: int, status: str | None = None) -> list[dict]:
    return [dict(row) for row in await overtime_request_repository.find_by_user(pool, user_id, status)]


async def get_pending(pool: asyncpg.Pool, reviewer: dict) -> list[dict]:
    return [dict(row) for row in await overtime_request_repository.find_pending(pool, reviewer)]
