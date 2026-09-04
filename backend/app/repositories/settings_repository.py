"""system_settings 表的資料存取（恆單列，id = 1）。"""

import asyncpg


async def get_settings(pool: asyncpg.Pool) -> asyncpg.Record:
    return await pool.fetchrow(
        """
        SELECT work_start_time, work_end_time, lunch_start_time, lunch_end_time,
               grace_period_minutes, updated_at
        FROM system_settings
        WHERE id = 1
        """
    )
