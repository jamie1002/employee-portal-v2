"""出勤異動查詢的範圍控管。

範圍限縮一律 **deny-by-default**：先把非 admin 一律限縮在自己（或自己的部門），
再逐一放寬，不要寫成「是 manager 才限縮」——後者一旦出現第四種身分就自動變成
不限縮（見 docs/PITFALLS.md C1）。
"""

from datetime import date

import asyncpg

from app.config.settings import app_settings
from app.repositories import attendance_repository, user_repository
from app.utils.errors import AppError


async def get_changes(
    pool: asyncpg.Pool,
    current_user: dict,
    user_id: int | None,
    department_id: int | None,
    start_date: date,
    end_date: date,
) -> list[dict]:
    role = current_user["role"]

    if role == "admin":
        if user_id is not None:
            user_ids = [user_id]
        else:
            members = await user_repository.find_all(pool, department_id=department_id)
            user_ids = [member["id"] for member in members]
    elif role == "manager":
        scope_department_id = current_user["department_id"]
        if scope_department_id is None:
            # 未指派部門的 manager 沒有可限縮的範圍，不得因此變成看全公司。
            raise AppError(403, "尚未指派部門，無法查詢出勤異動。", "FORBIDDEN")

        if user_id is not None:
            target = await user_repository.find_public_by_id(pool, user_id)
            if not target or target["department_id"] != scope_department_id:
                raise AppError(403, "僅能查詢所屬部門成員的出勤異動。", "FORBIDDEN")
            user_ids = [user_id]
        else:
            if department_id is not None and department_id != scope_department_id:
                raise AppError(403, "僅能查詢所屬部門成員的出勤異動。", "FORBIDDEN")
            members = await user_repository.find_all(pool, department_id=scope_department_id)
            user_ids = [member["id"] for member in members]
    else:
        # 一般員工：查詢對象一律取自 token，刻意不理會 user_id／department_id 參數。
        user_ids = [current_user["id"]]

    if not user_ids:
        return []

    rows = await attendance_repository.find_changes(
        pool, user_ids, start_date, end_date, app_settings.APP_TIMEZONE
    )
    return [dict(row) for row in rows]
