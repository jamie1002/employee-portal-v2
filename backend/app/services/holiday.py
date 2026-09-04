"""國定假日維護的業務邏輯（SPEC.md §4.9）。"""

from datetime import date

import asyncpg

from app.repositories import holiday_repository
from app.utils.errors import AppError


async def list_holidays(pool: asyncpg.Pool) -> list[dict]:
    return [dict(row) for row in await holiday_repository.find_all(pool)]


async def create_holiday(pool: asyncpg.Pool, holiday_date: date, name: str) -> dict:
    try:
        created = await holiday_repository.create(pool, holiday_date, name)
    except asyncpg.UniqueViolationError:
        raise AppError(409, "該日已登記為國定假日。", "HOLIDAY_ALREADY_EXISTS") from None
    return dict(created)


async def delete_holiday(pool: asyncpg.Pool, holiday_date: date) -> None:
    if not await holiday_repository.delete_by_date(pool, holiday_date):
        raise AppError(404, "找不到指定的國定假日。", "NOT_FOUND")
