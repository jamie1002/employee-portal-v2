"""room_bookings 表的資料存取。

`find_conflicts` 的判定式（`start_time < 新end AND end_time > 新start`）在半開區間
語意下必須與 DB 排除約束（`tstzrange(...,'[)') WITH &&`，見 001_baseline.sql）完全
等價，否則應用層預檢與資料庫層防線會判斷不一致。這支只是**第一層**（給人看的友善
訊息），INSERT 本身仍會被第二層的 `no_double_booking` 排除約束把關（SPEC.md §4.6
的 TOCTOU 說明）。
"""

from datetime import date, datetime

import asyncpg

from app.utils.pg_types import pg_date

_COLUMNS = """
    id, room_id, user_id, title, start_time, end_time, status, created_at, updated_at
"""


async def find_conflicts(
    pool: asyncpg.Pool, room_id: int, start_time: datetime, end_time: datetime
) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT rb.start_time, rb.end_time, u.name AS booked_by_name
        FROM room_bookings rb
        JOIN users u ON u.id = rb.user_id
        WHERE rb.room_id = $1
          AND rb.status = 'confirmed'
          AND rb.start_time < $3
          AND rb.end_time > $2
        """,
        room_id,
        start_time,
        end_time,
    )


async def find_by_date(
    pool: asyncpg.Pool, target_date: date, room_id: int | None = None, status: str | None = None
) -> list[asyncpg.Record]:
    """`status` 未指定時預設只回傳生效中的預約（不含已取消）。"""
    conditions = ["(rb.start_time AT TIME ZONE 'Asia/Taipei')::date = $1"]
    params: list = [pg_date(target_date)]
    if room_id is not None:
        params.append(room_id)
        conditions.append(f"rb.room_id = ${len(params)}")
    params.append(status or "confirmed")
    conditions.append(f"rb.status = ${len(params)}")

    return await pool.fetch(
        f"""
        SELECT rb.id, rb.room_id, rb.user_id, rb.title, rb.start_time, rb.end_time, rb.status,
               rb.created_at, rb.updated_at, r.name AS room_name, u.name AS booked_by_name
        FROM room_bookings rb
        JOIN rooms r ON r.id = rb.room_id
        JOIN users u ON u.id = rb.user_id
        WHERE {" AND ".join(conditions)}
        ORDER BY rb.start_time
        """,
        *params,
    )


async def create(
    pool: asyncpg.Pool, user_id: int, room_id: int, title: str, start_time: datetime, end_time: datetime
) -> asyncpg.Record:
    return await pool.fetchrow(
        f"""
        INSERT INTO room_bookings (room_id, user_id, title, start_time, end_time)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING {_COLUMNS}
        """,
        room_id,
        user_id,
        title,
        start_time,
        end_time,
    )


async def find_by_id(pool: asyncpg.Pool, booking_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(f"SELECT {_COLUMNS} FROM room_bookings WHERE id = $1", booking_id)


async def cancel_by_id(pool: asyncpg.Pool, booking_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"""
        UPDATE room_bookings SET status = 'cancelled'
        WHERE id = $1 AND status = 'confirmed'
        RETURNING {_COLUMNS}
        """,
        booking_id,
    )


async def delete_by_id(pool: asyncpg.Pool, booking_id: int) -> str | None:
    return await pool.fetchval("DELETE FROM room_bookings WHERE id = $1 RETURNING 'ok'", booking_id)


async def find_all_in_range(
    pool: asyncpg.Pool,
    start_date: date | None = None,
    end_date: date | None = None,
    room_id: int | None = None,
    department_id: int | None = None,
) -> list[asyncpg.Record]:
    """供匯出報表使用。`department_id` 篩的是**借用人**所屬部門，不是場地本身
    （場地不分部門）——SPEC.md §4.8 的部門範圍限縮，指的就是這一欄。"""
    conditions = ["1 = 1"]
    params: list = []
    if start_date is not None:
        params.append(pg_date(start_date))
        conditions.append(f"(rb.start_time AT TIME ZONE 'Asia/Taipei')::date >= ${len(params)}")
    if end_date is not None:
        params.append(pg_date(end_date))
        conditions.append(f"(rb.start_time AT TIME ZONE 'Asia/Taipei')::date <= ${len(params)}")
    if room_id is not None:
        params.append(room_id)
        conditions.append(f"rb.room_id = ${len(params)}")
    if department_id is not None:
        params.append(department_id)
        conditions.append(f"u.department_id = ${len(params)}")

    return await pool.fetch(
        f"""
        SELECT rb.id, rb.room_id, r.name AS room_name, rb.user_id, u.name AS booked_by_name,
               d.name AS department_name, rb.title, rb.start_time, rb.end_time, rb.status, rb.created_at
        FROM room_bookings rb
        JOIN rooms r ON r.id = rb.room_id
        JOIN users u ON u.id = rb.user_id
        LEFT JOIN departments d ON d.id = u.department_id
        WHERE {" AND ".join(conditions)}
        ORDER BY rb.start_time DESC
        """,
        *params,
    )
