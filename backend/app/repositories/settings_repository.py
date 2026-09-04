"""system_settings 表的資料存取（恆單列，id = 1）。"""

from datetime import time

import asyncpg

from app.utils.pg_types import pg_time


async def get_settings(pool: asyncpg.Pool) -> asyncpg.Record:
    return await pool.fetchrow(
        """
        SELECT work_start_time, work_end_time, lunch_start_time, lunch_end_time,
               grace_period_minutes, updated_at
        FROM system_settings
        WHERE id = 1
        """
    )


async def update_settings(
    pool: asyncpg.Pool,
    work_start_time: time,
    work_end_time: time,
    lunch_start_time: time,
    lunch_end_time: time,
    grace_period_minutes: int,
) -> asyncpg.Record:
    return await pool.fetchrow(
        """
        UPDATE system_settings
        SET work_start_time = $1, work_end_time = $2, lunch_start_time = $3,
            lunch_end_time = $4, grace_period_minutes = $5
        WHERE id = 1
        RETURNING work_start_time, work_end_time, lunch_start_time, lunch_end_time,
                  grace_period_minutes, updated_at
        """,
        pg_time(work_start_time),
        pg_time(work_end_time),
        pg_time(lunch_start_time),
        pg_time(lunch_end_time),
        grace_period_minutes,
    )
