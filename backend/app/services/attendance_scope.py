"""出勤類查詢的可見範圍解析（單一事實來源）。

出勤明細（`GET /api/attendance`）與出勤異動（`GET /api/attendance/changes`）共用這支，
不各自實作一份——權限判斷出現第二套實作是 `docs/PITFALLS.md` C1 記錄過的失敗模式：
兩份程式碼在寫下的當下一定一致，分歧發生在半年後只改了其中一份的時候。

範圍限縮一律 **deny-by-default**：先假設看不到，再依角色逐一放寬，不要寫成
「是 manager 才限縮」——後者一旦出現第四種身分就自動變成不限縮。
"""

from __future__ import annotations

import asyncpg

from app.repositories import user_repository
from app.utils.errors import AppError

_CROSS_DEPARTMENT_MESSAGE = "僅能查詢所屬部門成員的資料。"


async def resolve_visible_user_ids(
    pool: asyncpg.Pool,
    current_user: dict,
    user_id: int | None = None,
    department_id: int | None = None,
) -> list[int]:
    """回傳這位請求者在本次查詢條件下「允許看到」的 user_id 清單。

    回傳空清單代表條件合法但沒有符合的成員（例如空部門），呼叫端應視為查無資料；
    不允許的查詢一律拋 403，不會安靜地回空清單——兩者語意不同，混在一起會讓
    越權查詢看起來像「這個部門剛好沒人」。
    """
    role = current_user["role"]

    if role == "admin":
        if user_id is not None:
            return [user_id]
        members = await user_repository.find_all(pool, department_id=department_id)
        return [member["id"] for member in members]

    if role == "manager":
        scope_department_id = current_user["department_id"]
        if scope_department_id is None:
            # 未指派部門的 manager 沒有可限縮的範圍。這裡一定要擋下來：若讓它往下走，
            # `find_all(department_id=None)` 會被解讀成「不篩選部門」，於是一個沒有部門
            # 的主管反而拿到全公司資料——deny-by-default 寫反成 allow-by-default，
            # 而且不會報錯。
            raise AppError(403, "尚未指派部門，無法查詢。", "FORBIDDEN")

        if user_id is not None:
            target = await user_repository.find_public_by_id(pool, user_id)
            if not target or target["department_id"] != scope_department_id:
                raise AppError(403, _CROSS_DEPARTMENT_MESSAGE, "FORBIDDEN")
            return [user_id]

        if department_id is not None and department_id != scope_department_id:
            raise AppError(403, _CROSS_DEPARTMENT_MESSAGE, "FORBIDDEN")

        members = await user_repository.find_all(pool, department_id=scope_department_id)
        return [member["id"] for member in members]

    # 其餘角色（含未來新增的身分）一律只看得到自己，且刻意不理會傳入的
    # user_id／department_id——查詢對象取自 token，不取自請求參數。
    return [current_user["id"]]
