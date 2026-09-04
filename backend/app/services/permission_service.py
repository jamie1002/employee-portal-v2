"""細粒度權限下放的業務邏輯（見 SPEC.md §3.4）。"""

import asyncpg

from app.repositories import permission_repository, user_repository
from app.utils.errors import AppError


def _to_dict(row: asyncpg.Record) -> dict:
    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "email": row["email"],
        "permission": row["permission"],
        "granted_by": row["granted_by"],
        "granted_by_name": row["granted_by_name"],
        "granted_at": row["granted_at"],
    }


async def list_permissions(pool: asyncpg.Pool) -> list[dict]:
    rows = await permission_repository.list_all_granted(pool)
    return [_to_dict(row) for row in rows]


async def set_user_permissions(
    pool: asyncpg.Pool, target_user_id: int, permissions: list[str], granted_by: int
) -> list[dict]:
    role = await user_repository.find_role_by_id(pool, target_user_id)
    if role is None:
        raise AppError(404, "使用者不存在。", "NOT_FOUND")

    # admin 恆具備全部權限、不在 user_permissions 留列；因為只有 admin 能授權
    # 而 admin 又被擋在這裡，「自我提權」在結構上不可能發生（見 SPEC.md §3.4）。
    if role == "admin":
        raise AppError(400, "系統管理者恆具備全部權限，不需個別授予。", "ADMIN_PERMISSIONS_IMPLICIT")

    await permission_repository.replace_user_permissions(pool, target_user_id, permissions, granted_by)

    all_rows = await permission_repository.list_all_granted(pool)
    return [_to_dict(row) for row in all_rows if row["user_id"] == target_user_id]
