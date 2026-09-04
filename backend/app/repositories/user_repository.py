"""users 表的資料存取。不做授權判斷（範圍限縮是 service 的責任）。"""

import asyncpg


async def find_by_email(pool: asyncpg.Pool, email: str) -> asyncpg.Record | None:
    """登入用：一次把密碼雜湊與 permissions 一起帶出，避免驗證密碼後還要再查一次。"""
    return await pool.fetchrow(
        """
        SELECT
            u.id, u.name, u.email, u.password_hash, u.role, u.department_id, u.is_first_login,
            COALESCE(p.permissions, ARRAY[]::text[]) AS permissions
        FROM users u
        LEFT JOIN LATERAL (
            SELECT array_agg(permission ORDER BY permission) AS permissions
            FROM user_permissions
            WHERE user_id = u.id
        ) p ON true
        WHERE u.email = $1
        """,
        email,
    )


async def find_by_id_with_permissions(pool: asyncpg.Pool, user_id: int) -> asyncpg.Record | None:
    """回傳使用者資料，並用 LEFT JOIN LATERAL 一併帶出 permissions——這本來就是
    每個請求都要做一次的使用者查詢，權限用同一趟查詢帶出不增加往返（見 SPEC.md §3.2）。"""
    return await pool.fetchrow(
        """
        SELECT
            u.id, u.name, u.email, u.role, u.department_id, u.is_first_login,
            COALESCE(p.permissions, ARRAY[]::text[]) AS permissions
        FROM users u
        LEFT JOIN LATERAL (
            SELECT array_agg(permission ORDER BY permission) AS permissions
            FROM user_permissions
            WHERE user_id = u.id
        ) p ON true
        WHERE u.id = $1
        """,
        user_id,
    )


_PUBLIC_COLUMNS = """
    u.id, u.name, u.email, u.role, u.department_id, u.employee_no,
    u.extension_number, u.hire_date, d.name AS department_name
"""


async def find_by_ids(pool: asyncpg.Pool, user_ids: list[int]) -> list[asyncpg.Record]:
    """出勤查詢會一次解析多位使用者，需要姓名／員工編號／部門名稱等中繼資料。"""
    if not user_ids:
        return []
    return await pool.fetch(
        f"""
        SELECT {_PUBLIC_COLUMNS}
        FROM users u
        LEFT JOIN departments d ON d.id = u.department_id
        WHERE u.id = ANY($1::int[])
        """,
        user_ids,
    )


async def find_all(pool: asyncpg.Pool, department_id: int | None = None) -> list[asyncpg.Record]:
    return await pool.fetch(
        f"""
        SELECT {_PUBLIC_COLUMNS}
        FROM users u
        LEFT JOIN departments d ON d.id = u.department_id
        WHERE ($1::int IS NULL OR u.department_id = $1)
        ORDER BY u.employee_no NULLS LAST, u.id
        """,
        department_id,
    )


async def find_public_by_id(pool: asyncpg.Pool, user_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"""
        SELECT {_PUBLIC_COLUMNS}
        FROM users u
        LEFT JOIN departments d ON d.id = u.department_id
        WHERE u.id = $1
        """,
        user_id,
    )


async def find_credentials_by_id(pool: asyncpg.Pool, user_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT id, email, password_hash FROM users WHERE id = $1", user_id)


async def find_role_by_id(pool: asyncpg.Pool, user_id: int) -> str | None:
    return await pool.fetchval("SELECT role FROM users WHERE id = $1", user_id)


async def update_password(pool: asyncpg.Pool, user_id: int, password_hash: str) -> None:
    await pool.execute("UPDATE users SET password_hash = $1 WHERE id = $2", password_hash, user_id)
