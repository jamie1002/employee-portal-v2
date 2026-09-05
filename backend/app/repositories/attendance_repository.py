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
    require_field_null: str | None = None,
) -> asyncpg.Record | None:
    """寫入「實際打卡」這件原始事實（僅 punch_in()／punch_out() 呼叫）。

    `now` 由呼叫端傳入 get_virtual_now() 算出的值，明確寫入 created_at／updated_at：
    本表刻意沒有 updated_at 觸發器，因為觸發器內的 SQL now() 不知道虛擬時鐘的偏移量
    （見 docs/PITFALLS.md A3）。

    `require_field_null`：傳入 `"punch_in_time"` 或 `"punch_out_time"` 時，改用單一原子
    的 `INSERT ... ON CONFLICT DO UPDATE ... WHERE <欄位> IS NULL` 陳述式，guard 失敗
    （該欄位已經有值）時 `RETURNING` 不到列，回傳 `None` 交由呼叫端決定要回什麼錯誤。

    這是必要的：原本「先 SELECT 有沒有既有列、有就 UPDATE、沒有就 INSERT」這個決策本身
    橫跨兩個獨立陳述式，兩個並行的上班打卡都可能各自的 SELECT 先看到「沒有列」而各自
    決定要 INSERT——但真正執行到 INSERT 時，其中一個已經因為對方剛提交而改口說「喔，
    有列了，那我 UPDATE」，於是兩個都「成功」，`UNIQUE(user_id, punch_date)` 這道防線
    根本沒被真正踩到（實測過：`asyncio.gather` 兩個並行請求，在 CI 環境下確實會重現
    兩個都拿到 201，見 docs/PITFALLS.md A7）。改成單一陳述式的 `INSERT ... ON CONFLICT`
    後，PostgreSQL 保證同一時間只有一個交易能通過那個 `WHERE ... IS NULL` guard，另一個
    要嘛等前者提交後看到欄位已非 NULL 而不更新（`RETURNING` 不到列），沒有中間狀態可鑽。

    未傳 `require_field_null` 時維持原本「先查、有列就 UPDATE、沒有就 INSERT」的一般
    upsert 語意，供不需要並行安全（如種子腳本）的呼叫端使用。
    """
    if require_field_null is not None:
        if require_field_null not in ("punch_in_time", "punch_out_time"):
            raise ValueError(f"不支援的 require_field_null：{require_field_null!r}")
        guard_column = require_field_null
        return await pool.fetchrow(
            f"""
            INSERT INTO attendances (
                user_id, punch_date, punch_in_time, punch_out_time, status,
                work_hours, is_early_leave, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
            ON CONFLICT (user_id, punch_date) DO UPDATE
            SET punch_in_time = EXCLUDED.punch_in_time,
                punch_out_time = EXCLUDED.punch_out_time,
                status = EXCLUDED.status,
                work_hours = EXCLUDED.work_hours,
                is_early_leave = EXCLUDED.is_early_leave,
                updated_at = EXCLUDED.updated_at
            WHERE attendances.{guard_column} IS NULL
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
