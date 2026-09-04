"""overtime_requests 表的資料存取。"""

from datetime import datetime

import asyncpg

_COLUMNS = """
    id, user_id, start_time, end_time, hours,
    reason, status, reviewer_id, review_note, reviewed_at, created_at
"""


async def create(
    pool: asyncpg.Pool,
    user_id: int,
    start_time: datetime,
    end_time: datetime,
    hours: float,
    reason: str,
    created_at: datetime,
) -> asyncpg.Record:
    return await pool.fetchrow(
        f"""
        INSERT INTO overtime_requests (user_id, start_time, end_time, hours, reason, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING {_COLUMNS}
        """,
        user_id,
        start_time,
        end_time,
        hours,
        reason,
        created_at,
    )


async def find_by_id(pool: asyncpg.Pool, request_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT ovr.id, ovr.user_id, ovr.start_time, ovr.end_time, ovr.hours,
               ovr.reason, ovr.status, ovr.reviewer_id, ovr.review_note, ovr.reviewed_at, ovr.created_at,
               u.department_id AS applicant_department_id
        FROM overtime_requests ovr
        JOIN users u ON u.id = ovr.user_id
        WHERE ovr.id = $1
        """,
        request_id,
    )


async def find_by_user(pool: asyncpg.Pool, user_id: int, status: str | None = None) -> list[asyncpg.Record]:
    conditions = "ovr.user_id = $1" + (" AND ovr.status = $2" if status else "")
    params = [user_id] + ([status] if status else [])
    return await pool.fetch(
        f"""
        SELECT ovr.id, ovr.user_id, ovr.start_time, ovr.end_time, ovr.hours,
               ovr.reason, ovr.status, ovr.reviewer_id, ovr.review_note, ovr.reviewed_at, ovr.created_at,
               u.name AS applicant_name, d.name AS department_name, reviewer.name AS reviewer_name
        FROM overtime_requests ovr
        JOIN users u ON u.id = ovr.user_id
        LEFT JOIN departments d ON d.id = u.department_id
        LEFT JOIN users reviewer ON reviewer.id = ovr.reviewer_id
        WHERE {conditions}
        ORDER BY ovr.created_at DESC
        """,
        *params,
    )


async def find_pending(pool: asyncpg.Pool, reviewer: dict) -> list[asyncpg.Record]:
    base_select = """
        SELECT ovr.id, ovr.user_id, ovr.start_time, ovr.end_time, ovr.hours,
               ovr.reason, ovr.status, ovr.reviewer_id, ovr.review_note, ovr.reviewed_at, ovr.created_at,
               u.name AS applicant_name, d.name AS department_name
        FROM overtime_requests ovr
        JOIN users u ON u.id = ovr.user_id
        LEFT JOIN departments d ON d.id = u.department_id
        WHERE ovr.status = 'pending'
    """
    if reviewer["role"] == "admin":
        return await pool.fetch(base_select + " ORDER BY ovr.created_at ASC")
    return await pool.fetch(
        base_select + " AND ovr.user_id <> $1 AND u.department_id = $2 ORDER BY ovr.created_at ASC",
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
        UPDATE overtime_requests
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
