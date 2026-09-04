"""rooms 表的資料存取。純清單查詢，沒有寫入 API（場地本身由種子資料固定）。"""

import asyncpg

_COLUMNS = "id, name, capacity, location_info, created_at"


async def find_all(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch(f"SELECT {_COLUMNS} FROM rooms ORDER BY id")


async def find_by_id(pool: asyncpg.Pool, room_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(f"SELECT {_COLUMNS} FROM rooms WHERE id = $1", room_id)
