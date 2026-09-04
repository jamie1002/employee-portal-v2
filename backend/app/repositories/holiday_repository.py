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


async def find_all(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch("SELECT holiday_date, name, created_at FROM holidays ORDER BY holiday_date")


async def create(pool: asyncpg.Pool, holiday_date: date, name: str) -> asyncpg.Record:
    return await pool.fetchrow(
        "INSERT INTO holidays (holiday_date, name) VALUES ($1, $2) RETURNING holiday_date, name, created_at",
        pg_date(holiday_date),
        name,
    )


async def delete_by_date(pool: asyncpg.Pool, holiday_date: date) -> bool:
    result = await pool.execute("DELETE FROM holidays WHERE holiday_date = $1", pg_date(holiday_date))
    return result != "DELETE 0"
