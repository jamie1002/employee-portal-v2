"""attendances 表的資料存取。

本表**只保存原始打卡事實**：補打卡與請假核准都不寫回這裡，異動後的生效值由
services/attendance_effective.py 於讀取時 join 已核准申請單即時算出（SPEC.md §4.2）。
因此這裡的查詢結果一律是原始值，寫入端也不需要 merge 分支。
"""

from datetime import date, datetime

import asyncpg

from app.utils.pg_types import pg_date

COLUMNS = """
    id, user_id, punch_date, punch_in_time, punch_out_time, status,
    work_hours, is_early_leave, note, created_at, updated_at
"""


async def find_by_user_and_date(pool: asyncpg.Pool, user_id: int, punch_date: date) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"SELECT {COLUMNS} FROM attendances WHERE user_id = $1 AND punch_date = $2",
        user_id,
        pg_date(punch_date),
    )


async def find_by_users_in_range(
    pool: asyncpg.Pool, user_ids: list[int], start_date: date, end_date: date
) -> list[asyncpg.Record]:
    """一次撈回多位使用者在區間內的全部原始出勤列，不分頁——分頁在應用層做
    （量體是「每人每月約 22 個工作日」，全量撈回沒有效能疑慮）。"""
    if not user_ids:
        return []
    return await pool.fetch(
        f"""
        SELECT {COLUMNS} FROM attendances
        WHERE user_id = ANY($1::int[]) AND punch_date >= $2 AND punch_date <= $3
        """,
        user_ids,
        pg_date(start_date),
        pg_date(end_date),
    )


async def find_changes(
    pool: asyncpg.Pool, user_ids: list[int], start_date: date, end_date: date, tz: str
) -> list[asyncpg.Record]:
    """出勤異動：UNION 補打卡與請假兩張申請單，供畫面依 (user_id, 日期) 分組呈現。

    刻意不新增稽核表——目前沒有繞過申請單直接改動出勤的路徑，每筆異動都能從這
    兩張申請單完整回推，多一張表只會多一個需要同步維護的真相來源。
    """
    if not user_ids:
        return []
    return await pool.fetch(
        """
        SELECT 'punch_request' AS source, pr.id AS request_id, pr.user_id,
               applicant.employee_no, applicant.name AS user_name, d.name AS department_name,
               pr.target_date AS start_date, pr.target_date AS end_date,
               pr.status, pr.created_at AS submitted_at, pr.reviewed_at, pr.review_note,
               reviewer.name AS reviewer_name,
               pr.type AS punch_type, pr.requested_in_time, pr.requested_out_time,
               NULL::text AS leave_type, NULL::numeric AS hours, pr.reason,
               NULL::timestamptz AS leave_start_time, NULL::timestamptz AS leave_end_time
        FROM punch_requests pr
        JOIN users applicant ON applicant.id = pr.user_id
        LEFT JOIN departments d ON d.id = applicant.department_id
        LEFT JOIN users reviewer ON reviewer.id = pr.reviewer_id
        WHERE pr.user_id = ANY($1::int[]) AND pr.target_date >= $2 AND pr.target_date <= $3

        UNION ALL

        SELECT 'leave_request' AS source, lr.id AS request_id, lr.user_id,
               applicant.employee_no, applicant.name AS user_name, d.name AS department_name,
               (lr.start_time AT TIME ZONE $4)::date AS start_date,
               (lr.end_time AT TIME ZONE $4)::date AS end_date,
               lr.status, lr.created_at AS submitted_at, lr.reviewed_at, lr.review_note,
               reviewer.name AS reviewer_name,
               NULL::text AS punch_type, NULL::timestamptz AS requested_in_time,
               NULL::timestamptz AS requested_out_time,
               lr.leave_type, lr.hours, lr.reason,
               lr.start_time AS leave_start_time, lr.end_time AS leave_end_time
        FROM leave_requests lr
        JOIN users applicant ON applicant.id = lr.user_id
        LEFT JOIN departments d ON d.id = applicant.department_id
        LEFT JOIN users reviewer ON reviewer.id = lr.reviewer_id
        WHERE lr.user_id = ANY($1::int[])
          AND (lr.start_time AT TIME ZONE $4)::date <= $3
          AND (lr.end_time AT TIME ZONE $4)::date >= $2

        ORDER BY submitted_at DESC
        """,
        user_ids,
        pg_date(start_date),
        pg_date(end_date),
        tz,
    )


async def upsert_attendance(
    pool: asyncpg.Pool,
    user_id: int,
    punch_date: date,
    punch_in_time: datetime | None,
    punch_out_time: datetime | None,
    status: str,
    work_hours: float | None,
    now: datetime,
    is_early_leave: bool = False,
) -> asyncpg.Record:
    """寫入「實際打卡」這件原始事實（僅 punch_in()／punch_out() 呼叫）。

    `now` 由呼叫端傳入 get_virtual_now() 算出的值，明確寫入 created_at／updated_at：
    本表刻意沒有 updated_at 觸發器，因為觸發器內的 SQL now() 不知道虛擬時鐘的偏移量
    （見 docs/PITFALLS.md A3）。

    **刻意不用 `INSERT ... ON CONFLICT DO UPDATE`**：那會讓兩個並行的上班打卡都「成功」
    （後到的那筆變成 UPDATE 覆蓋先到的），等於自己拆掉 `UNIQUE(user_id, punch_date)`
    這道 TOCTOU 防線。維持「先查、有列就 UPDATE、沒有就 INSERT」，並行時後到的
    INSERT 會撞上唯一鍵拋 23505，由錯誤中介層轉譯成 409，正是我們要的行為。
    存在但還沒有上班時間的列（例如曠職排程補的 absent 列，虛擬時鐘往回撥後又去打卡）
    則走 UPDATE 分支，不會被誤判成「今日已完成上班打卡」。
    """
    existing_id = await pool.fetchval(
        "SELECT id FROM attendances WHERE user_id = $1 AND punch_date = $2",
        user_id,
        pg_date(punch_date),
    )

    if existing_id is not None:
        return await pool.fetchrow(
            f"""
            UPDATE attendances
            SET punch_in_time = $1, punch_out_time = $2, status = $3,
                work_hours = $4, is_early_leave = $5, updated_at = $6
            WHERE id = $7
            RETURNING {COLUMNS}
            """,
            punch_in_time,
            punch_out_time,
            status,
            work_hours,
            is_early_leave,
            now,
            existing_id,
        )

    return await pool.fetchrow(
        f"""
        INSERT INTO attendances (
            user_id, punch_date, punch_in_time, punch_out_time, status,
            work_hours, is_early_leave, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
        RETURNING {COLUMNS}
        """,
        user_id,
        pg_date(punch_date),
        punch_in_time,
        punch_out_time,
        status,
        work_hours,
        is_early_leave,
        now,
    )


async def set_note(
    pool: asyncpg.Pool, user_id: int, punch_date: date, note: str, now: datetime
) -> asyncpg.Record | None:
    """寫入當日出勤備註。備註依附在當日的原始出勤列上，尚未打上班卡（沒有出勤列）
    時回傳 None，呼叫端據此回 400。"""
    return await pool.fetchrow(
        f"""
        UPDATE attendances SET note = $1, updated_at = $2
        WHERE user_id = $3 AND punch_date = $4
        RETURNING {COLUMNS}
        """,
        note,
        now,
        user_id,
        pg_date(punch_date),
    )
