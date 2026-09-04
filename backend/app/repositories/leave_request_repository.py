"""leave_requests 表的資料存取。"""

from datetime import date, datetime

import asyncpg

from app.utils.pg_types import pg_date

_INTERVAL_COLUMNS = "user_id, start_time, end_time"
_COLUMNS = """
    id, user_id, leave_type, start_time, end_time, hours,
    reason, status, reviewer_id, review_note, reviewed_at, created_at
"""


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


async def exists_pending_covering_date(pool: asyncpg.Pool, user_id: int, punch_date: date, tz: str) -> bool:
    """供加班申請的起算點防呆使用：當天有待審請假時先擋下（見 services/overtime_request.py）。"""
    found = await pool.fetchval(
        """
        SELECT 1 FROM leave_requests
        WHERE user_id = $1 AND status = 'pending'
          AND (start_time AT TIME ZONE $3)::date <= $2
          AND (end_time AT TIME ZONE $3)::date >= $2
        """,
        user_id,
        pg_date(punch_date),
        tz,
    )
    return found is not None


async def sum_approved_hours_in_period(
    pool: asyncpg.Pool, user_id: int, leave_type: str, period_start_utc: datetime, period_end_utc: datetime
) -> float:
    """供假別配額計算使用：某假別在 [period_start, period_end) 內已核准的時數總和。"""
    value = await pool.fetchval(
        """
        SELECT COALESCE(SUM(hours), 0) FROM leave_requests
        WHERE user_id = $1 AND leave_type = $2 AND status = 'approved'
          AND start_time >= $3 AND start_time < $4
        """,
        user_id,
        leave_type,
        period_start_utc,
        period_end_utc,
    )
    return float(value)


async def create(
    pool: asyncpg.Pool,
    user_id: int,
    leave_type: str,
    start_time: datetime,
    end_time: datetime,
    hours: float,
    reason: str,
    created_at: datetime,
) -> asyncpg.Record:
    return await pool.fetchrow(
        f"""
        INSERT INTO leave_requests (user_id, leave_type, start_time, end_time, hours, reason, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING {_COLUMNS}
        """,
        user_id,
        leave_type,
        start_time,
        end_time,
        hours,
        reason,
        created_at,
    )


async def find_by_id(pool: asyncpg.Pool, request_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT lr.id, lr.user_id, lr.leave_type, lr.start_time, lr.end_time, lr.hours,
               lr.reason, lr.status, lr.reviewer_id, lr.review_note, lr.reviewed_at, lr.created_at,
               u.department_id AS applicant_department_id
        FROM leave_requests lr
        JOIN users u ON u.id = lr.user_id
        WHERE lr.id = $1
        """,
        request_id,
    )


async def find_by_user(pool: asyncpg.Pool, user_id: int, status: str | None = None) -> list[asyncpg.Record]:
    conditions = "lr.user_id = $1" + (" AND lr.status = $2" if status else "")
    params = [user_id] + ([status] if status else [])
    return await pool.fetch(
        f"""
        SELECT lr.id, lr.user_id, lr.leave_type, lr.start_time, lr.end_time, lr.hours,
               lr.reason, lr.status, lr.reviewer_id, lr.review_note, lr.reviewed_at, lr.created_at,
               u.name AS applicant_name, d.name AS department_name, reviewer.name AS reviewer_name
        FROM leave_requests lr
        JOIN users u ON u.id = lr.user_id
        LEFT JOIN departments d ON d.id = u.department_id
        LEFT JOIN users reviewer ON reviewer.id = lr.reviewer_id
        WHERE {conditions}
        ORDER BY lr.created_at DESC
        """,
        *params,
    )


async def find_pending(pool: asyncpg.Pool, reviewer: dict) -> list[asyncpg.Record]:
    base_select = """
        SELECT lr.id, lr.user_id, lr.leave_type, lr.start_time, lr.end_time, lr.hours,
               lr.reason, lr.status, lr.reviewer_id, lr.review_note, lr.reviewed_at, lr.created_at,
               u.name AS applicant_name, d.name AS department_name
        FROM leave_requests lr
        JOIN users u ON u.id = lr.user_id
        LEFT JOIN departments d ON d.id = u.department_id
        WHERE lr.status = 'pending'
    """
    if reviewer["role"] == "admin":
        return await pool.fetch(base_select + " ORDER BY lr.created_at ASC")
    return await pool.fetch(
        base_select + " AND lr.user_id <> $1 AND u.department_id = $2 ORDER BY lr.created_at ASC",
        reviewer["id"],
        reviewer["department_id"],
    )


async def update_review(
    pool: asyncpg.Pool,
    request_id: int,
    status: str,
    reviewer_id: int,
    review_note: str | None,
    reviewed_at: datetime,
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"""
        UPDATE leave_requests
        SET status = $1, reviewer_id = $2, review_note = $3, reviewed_at = $4
        WHERE id = $5 AND status = 'pending'
        RETURNING {_COLUMNS}
        """,
        status,
        reviewer_id,
        review_note,
        reviewed_at,
        request_id,
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
