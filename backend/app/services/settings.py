"""考勤設定的業務邏輯（SPEC.md §6.6）。修改僅影響後續打卡，不回溯重算歷史紀錄。"""

from datetime import time

import asyncpg

from app.repositories import settings_repository


async def get_settings(pool: asyncpg.Pool) -> dict:
    return dict(await settings_repository.get_settings(pool))


async def update_settings(
    pool: asyncpg.Pool,
    work_start_time: time,
    work_end_time: time,
    lunch_start_time: time,
    lunch_end_time: time,
    grace_period_minutes: int,
) -> dict:
    updated = await settings_repository.update_settings(
        pool, work_start_time, work_end_time, lunch_start_time, lunch_end_time, grace_period_minutes
    )
    return dict(updated)
