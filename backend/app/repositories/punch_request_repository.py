"""punch_requests 表的資料存取。

批 2 只需要「讀」——出勤生效值解析要 join 已核准的補打卡；建立與審核申請單是批 3。
"""

from datetime import date

import asyncpg

from app.utils.pg_types import pg_date


async def find_approved_in_range(
    pool: asyncpg.Pool, user_ids: list[int], start_date: date, end_date: date
) -> list[asyncpg.Record]:
    """已核准的補打卡：每個 (user_id, target_date) 至多一筆有效值。"""
    if not user_ids:
        return []
    return await pool.fetch(
        """
        SELECT user_id, target_date, type, requested_in_time, requested_out_time
        FROM punch_requests
        WHERE user_id = ANY($1::int[])
          AND status = 'approved'
          AND target_date >= $2 AND target_date <= $3
        ORDER BY reviewed_at
        """,
        user_ids,
        pg_date(start_date),
        pg_date(end_date),
    )


async def find_target_dates_in_range(
    pool: asyncpg.Pool, user_ids: list[int], start_date: date, end_date: date
) -> list[asyncpg.Record]:
    """**不分狀態**的補打卡目標日期，供標記 has_changes 使用——待審與已駁回的
    申請也該讓使用者看得出「這天有動過」（與 is_adjusted 語意不同，見 SPEC.md §4.2）。
    """
    if not user_ids:
        return []
    return await pool.fetch(
        """
        SELECT DISTINCT user_id, target_date
        FROM punch_requests
        WHERE user_id = ANY($1::int[]) AND target_date >= $2 AND target_date <= $3
        """,
        user_ids,
        pg_date(start_date),
        pg_date(end_date),
    )
