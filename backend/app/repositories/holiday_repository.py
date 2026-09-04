"""holidays 表的資料存取。批 2 只需要讀取；維護 API 在批 5。"""

from datetime import date

import asyncpg

from app.utils.pg_types import pg_date


async def exists(pool: asyncpg.Pool, holiday_date: date) -> bool:
    found = await pool.fetchval(
        "SELECT 1 FROM holidays WHERE holiday_date = $1", pg_date(holiday_date)
    )
    return found is not None


async def find_dates_in_range(pool: asyncpg.Pool, start_date: date, end_date: date) -> list[date]:
    rows = await pool.fetch(
        """
        SELECT holiday_date FROM holidays
        WHERE holiday_date >= $1 AND holiday_date <= $2
        ORDER BY holiday_date
        """,
        pg_date(start_date),
        pg_date(end_date),
    )
    return [row["holiday_date"] for row in rows]
