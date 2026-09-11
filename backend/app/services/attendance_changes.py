"""出勤異動查詢。

可見範圍的解析共用 `attendance_scope.resolve_visible_user_ids()`，與出勤明細
（`services/attendance.py` 的 `get_all()`）是同一份實作，不各自維護一套
（見 docs/PITFALLS.md C1）。
"""

from datetime import date

import asyncpg

from app.config.settings import app_settings
from app.repositories import attendance_repository
from app.services import attendance_scope


async def get_changes(
    pool: asyncpg.Pool,
    current_user: dict,
    user_id: int | None,
    department_id: int | None,
    start_date: date,
    end_date: date,
) -> list[dict]:
    user_ids = await attendance_scope.resolve_visible_user_ids(
        pool, current_user, user_id, department_id
    )

    if not user_ids:
        return []

    rows = await attendance_repository.find_changes(
        pool, user_ids, start_date, end_date, app_settings.APP_TIMEZONE
    )
    return [dict(row) for row in rows]
