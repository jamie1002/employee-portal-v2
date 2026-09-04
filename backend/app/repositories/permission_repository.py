"""user_permissions 表的資料存取。不做授權判斷。"""

import asyncpg


async def list_all_granted(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT
            up.user_id, u.name, u.email, up.permission,
            up.granted_by, gu.name AS granted_by_name, up.granted_at
        FROM user_permissions up
        JOIN users u ON u.id = up.user_id
        LEFT JOIN users gu ON gu.id = up.granted_by
        ORDER BY up.user_id, up.permission
        """
    )


async def replace_user_permissions(
    pool: asyncpg.Pool, user_id: int, permissions: list[str], granted_by: int
) -> None:
    """整組取代，但服務層用 diff 實作：未變動的權限靠 ON CONFLICT DO NOTHING
    原封不動保留原本的 granted_by／granted_at，不是「先刪光再全部插入」
    （見 docs/PITFALLS.md C5）。"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM user_permissions WHERE user_id = $1 AND permission <> ALL($2::text[])",
                user_id,
                permissions,
            )
            if permissions:
                await conn.execute(
                    """
                    INSERT INTO user_permissions (user_id, permission, granted_by)
                    SELECT $1, p, $3 FROM unnest($2::text[]) AS p
                    ON CONFLICT (user_id, permission) DO NOTHING
                    """,
                    user_id,
                    permissions,
                    granted_by,
                )
