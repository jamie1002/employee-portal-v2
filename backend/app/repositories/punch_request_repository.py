"""punch_requests 表的資料存取。"""

from datetime import date, datetime

import asyncpg

from app.utils.pg_types import pg_date

_COLUMNS = """
    id, user_id, target_date, type, requested_in_time, requested_out_time,
    reason, status, reviewer_id, review_note, reviewed_at, created_at
"""


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


async def has_active_request_for_date(pool: asyncpg.Pool, user_id: int, target_date: date) -> bool:
    """同一天已有一筆待審或已核准的補打卡申請時，拒絕新增（SPEC.md §4.5）。"""
    found = await pool.fetchval(
        "SELECT 1 FROM punch_requests WHERE user_id = $1 AND target_date = $2 AND status IN ('pending', 'approved')",
        user_id,
        pg_date(target_date),
    )
    return found is not None


async def exists_pending_for_date(pool: asyncpg.Pool, user_id: int, target_date: date) -> bool:
    """供加班申請的起算點防呆使用：當天有待審補打卡時先擋下（見 services/overtime_request.py）。"""
    found = await pool.fetchval(
        "SELECT 1 FROM punch_requests WHERE user_id = $1 AND target_date = $2 AND status = 'pending'",
        user_id,
        pg_date(target_date),
    )
    return found is not None


async def create(
    pool: asyncpg.Pool,
    user_id: int,
    punch_type: str,
    target_date: date,
    requested_in_time: datetime | None,
    requested_out_time: datetime | None,
    reason: str,
    created_at: datetime,
) -> asyncpg.Record:
    return await pool.fetchrow(
        f"""
        INSERT INTO punch_requests (
            user_id, target_date, type, requested_in_time, requested_out_time, reason, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING {_COLUMNS}
        """,
        user_id,
        pg_date(target_date),
        punch_type,
        requested_in_time,
        requested_out_time,
        reason,
        created_at,
    )


async def find_by_id(pool: asyncpg.Pool, request_id: int) -> asyncpg.Record | None:
    """附帶申請人所屬部門 id，供 request_review 的跨部門審核檢查使用。"""
    return await pool.fetchrow(
        """
        SELECT pr.id, pr.user_id, pr.target_date, pr.type, pr.requested_in_time, pr.requested_out_time,
               pr.reason, pr.status, pr.reviewer_id, pr.review_note, pr.reviewed_at, pr.created_at,
               u.department_id AS applicant_department_id
        FROM punch_requests pr
        JOIN users u ON u.id = pr.user_id
        WHERE pr.id = $1
        """,
        request_id,
    )


async def find_by_user(pool: asyncpg.Pool, user_id: int, status: str | None = None) -> list[asyncpg.Record]:
    conditions = "pr.user_id = $1" + (" AND pr.status = $2" if status else "")
    params = [user_id] + ([status] if status else [])
    return await pool.fetch(
        f"""
        SELECT pr.id, pr.user_id, pr.target_date, pr.type, pr.requested_in_time, pr.requested_out_time,
               pr.reason, pr.status, pr.reviewer_id, pr.review_note, pr.reviewed_at, pr.created_at,
               u.name AS applicant_name, d.name AS department_name, reviewer.name AS reviewer_name
        FROM punch_requests pr
        JOIN users u ON u.id = pr.user_id
        LEFT JOIN departments d ON d.id = u.department_id
        LEFT JOIN users reviewer ON reviewer.id = pr.reviewer_id
        WHERE {conditions}
        ORDER BY pr.created_at DESC
        """,
        *params,
    )


async def find_pending(pool: asyncpg.Pool, reviewer: dict) -> list[asyncpg.Record]:
    """待審清單：manager 限所屬部門，且固定排除自己送出的申請；admin 是唯一管理者、
    沒有代理人審核自己的申請，故不排除（SPEC.md §3.3）。"""
    base_select = """
        SELECT pr.id, pr.user_id, pr.target_date, pr.type, pr.requested_in_time, pr.requested_out_time,
               pr.reason, pr.status, pr.reviewer_id, pr.review_note, pr.reviewed_at, pr.created_at,
               u.name AS applicant_name, d.name AS department_name
        FROM punch_requests pr
        JOIN users u ON u.id = pr.user_id
        LEFT JOIN departments d ON d.id = u.department_id
        WHERE pr.status = 'pending'
    """
    if reviewer["role"] == "admin":
        return await pool.fetch(base_select + " ORDER BY pr.created_at ASC")
    return await pool.fetch(
        base_select + " AND pr.user_id <> $1 AND u.department_id = $2 ORDER BY pr.created_at ASC",
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
    """`WHERE status = 'pending'` 是防止並行審核的最終防線：兩個審核者同時通過
    應用層的狀態檢查後，只有一個 UPDATE 真正命中列，另一個回傳 None（見
    services/request_review.py 轉譯成 409）。"""
    return await pool.fetchrow(
        f"""
        UPDATE punch_requests
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
