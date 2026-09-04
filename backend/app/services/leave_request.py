"""請假申請的業務邏輯（SPEC.md §4.3 §4.5）。

核准不覆寫 attendances——核准只更新申請單本身的狀態，出勤畫面的「生效狀態／
工時」一律由 services/attendance_effective.py 於讀取時 join 已核准請假即時算出。
"""

from datetime import datetime

import asyncpg

from app.config.settings import app_settings
from app.repositories import holiday_repository, leave_request_repository, settings_repository
from app.services.leave_hours import calculate_leave_hours
from app.services.work_hours import WorkSettings
from app.utils.errors import AppError
from app.utils.timezone import get_business_date


async def create(
    pool: asyncpg.Pool,
    user_id: int,
    leave_type: str,
    start_time: datetime,
    end_time: datetime,
    reason: str,
    created_at: datetime,
) -> dict:
    tz = app_settings.APP_TIMEZONE
    settings = WorkSettings.from_row(await settings_repository.get_settings(pool))

    from_date = get_business_date(start_time, tz=tz)
    to_date = get_business_date(end_time, tz=tz)
    holiday_dates = set(await holiday_repository.find_dates_in_range(pool, from_date, to_date))

    hours = calculate_leave_hours(start_time, end_time, settings, tz, holiday_dates)
    if hours <= 0:
        raise AppError(400, "所選區間不含任何工作日，無法計算請假時數。", "VALIDATION_ERROR")

    request = await leave_request_repository.create(
        pool, user_id, leave_type, start_time, end_time, hours, reason, created_at
    )
    return dict(request)


async def get_my_requests(pool: asyncpg.Pool, user_id: int, status: str | None = None) -> list[dict]:
    return [dict(row) for row in await leave_request_repository.find_by_user(pool, user_id, status)]


async def get_pending(pool: asyncpg.Pool, reviewer: dict) -> list[dict]:
    return [dict(row) for row in await leave_request_repository.find_pending(pool, reviewer)]
