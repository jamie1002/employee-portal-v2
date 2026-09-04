"""departments 表的資料存取。不做授權判斷。"""

import asyncpg

_LIST_QUERY = """
    SELECT d.id, d.name, d.manager_id, m.name AS manager_name,
           count(u.id) AS member_count
    FROM departments d
    LEFT JOIN users m ON m.id = d.manager_id
    LEFT JOIN users u ON u.department_id = d.id
    GROUP BY d.id, m.name
    ORDER BY d.id
"""


async def find_all(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch(_LIST_QUERY)


async def find_by_id(pool: asyncpg.Pool, department_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT d.id, d.name, d.manager_id, m.name AS manager_name, count(u.id) AS member_count
        FROM departments d
        LEFT JOIN users m ON m.id = d.manager_id
        LEFT JOIN users u ON u.department_id = d.id
        WHERE d.id = $1
        GROUP BY d.id, m.name
        """,
        department_id,
    )


async def create(pool: asyncpg.Pool, name: str, manager_id: int | None) -> int:
    return await pool.fetchval(
        "INSERT INTO departments (name, manager_id) VALUES ($1, $2) RETURNING id", name, manager_id
    )


async def update(pool: asyncpg.Pool, department_id: int, name: str, manager_id: int | None) -> bool:
    result = await pool.execute(
        "UPDATE departments SET name = $2, manager_id = $3 WHERE id = $1", department_id, name, manager_id
    )
    return result != "UPDATE 0"


async def delete_by_id(pool: asyncpg.Pool, department_id: int) -> bool:
    """成員的 department_id 由外鍵 `ON DELETE SET NULL` 處理，這裡不需要另外清理。"""
    result = await pool.execute("DELETE FROM departments WHERE id = $1", department_id)
    return result != "DELETE 0"
