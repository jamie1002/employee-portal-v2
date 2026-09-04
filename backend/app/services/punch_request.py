"""補打卡申請的業務邏輯（SPEC.md §4.5）。"""

from datetime import date, datetime

import asyncpg

from app.repositories import punch_request_repository
from app.utils.errors import AppError


async def create(
    pool: asyncpg.Pool,
    user_id: int,
    punch_type: str,
    target_date: date,
    requested_in_time: datetime | None,
    requested_out_time: datetime | None,
    reason: str,
    created_at: datetime,
) -> dict:
    if await punch_request_repository.has_active_request_for_date(pool, user_id, target_date):
        raise AppError(409, "這天已經有一筆待審或已核准的補打卡申請。", "DUPLICATE_PUNCH_REQUEST")

    request = await punch_request_repository.create(
        pool, user_id, punch_type, target_date, requested_in_time, requested_out_time, reason, created_at
    )
    return dict(request)


async def get_my_requests(pool: asyncpg.Pool, user_id: int, status: str | None = None) -> list[dict]:
    return [dict(row) for row in await punch_request_repository.find_by_user(pool, user_id, status)]


async def get_pending(pool: asyncpg.Pool, reviewer: dict) -> list[dict]:
    return [dict(row) for row in await punch_request_repository.find_pending(pool, reviewer)]
