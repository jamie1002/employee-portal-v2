"""leave_requests 表的資料存取。

批 2 只需要「讀」——出勤的應到班時間、當日應工時、生效狀態都要 join 已核准請假；
建立與審核申請單是批 3。
"""

from datetime import date

import asyncpg

from app.utils.pg_types import pg_date

_INTERVAL_COLUMNS = "user_id, start_time, end_time"


async def find_approved_intervals_for_date(
    pool: asyncpg.Pool, user_id: int, punch_date: date, tz: str
) -> list[tuple]:
    """單一使用者、單一日期的已核准請假區間（供打卡當下計算應到班時間與應工時）。"""
    rows = await pool.fetch(
        f"""
        SELECT {_INTERVAL_COLUMNS} FROM leave_requests
        WHERE user_id = $1 AND status = 'approved'
          AND (start_time AT TIME ZONE $3)::date <= $2
          AND (end_time AT TIME ZONE $3)::date >= $2
        ORDER BY start_time
        """,
        user_id,
        pg_date(punch_date),
        tz,
    )
    return [(row["start_time"], row["end_time"]) for row in rows]


async def find_approved_intervals_in_range(
    pool: asyncpg.Pool, user_ids: list[int], start_date: date, end_date: date, tz: str
) -> list[asyncpg.Record]:
    if not user_ids:
        return []
    return await pool.fetch(
        f"""
        SELECT {_INTERVAL_COLUMNS} FROM leave_requests
        WHERE user_id = ANY($1::int[]) AND status = 'approved'
          AND (start_time AT TIME ZONE $4)::date <= $3
          AND (end_time AT TIME ZONE $4)::date >= $2
        ORDER BY start_time
        """,
        user_ids,
        pg_date(start_date),
        pg_date(end_date),
        tz,
    )


async def find_any_status_intervals_in_range(
    pool: asyncpg.Pool, user_ids: list[int], start_date: date, end_date: date, tz: str
) -> list[asyncpg.Record]:
    """**不分狀態**的請假區間，供標記 has_changes 使用（見 punch_request_repository
    的同名說明）。"""
    if not user_ids:
        return []
    return await pool.fetch(
        f"""
        SELECT {_INTERVAL_COLUMNS} FROM leave_requests
        WHERE user_id = ANY($1::int[])
          AND (start_time AT TIME ZONE $4)::date <= $3
          AND (end_time AT TIME ZONE $4)::date >= $2
        """,
        user_ids,
        pg_date(start_date),
        pg_date(end_date),
        tz,
    )
