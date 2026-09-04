"""工作日判定：非週末且不在 holidays 表中。"""

from datetime import date

import asyncpg

from app.repositories import holiday_repository


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5  # Monday=0 ... Sunday=6


async def is_workday(pool: asyncpg.Pool, day: date) -> bool:
    if is_weekend(day):
        return False
    return not await holiday_repository.exists(pool, day)
