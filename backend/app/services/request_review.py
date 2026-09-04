"""三種申請單（補打卡／請假／加班）共用的審核狀態機（SPEC.md §4.5）。

對申請類型保持無知：只依賴呼叫端傳入的 repo 模組提供 `find_by_id(pool, id)` 與
`update_review(pool, id, status, reviewer_id, review_note, reviewed_at)` 兩個函式，
簽章一致即可（punch_request_repository／leave_request_repository／
overtime_request_repository 三者皆符合）。
"""

from types import ModuleType

import asyncpg

from app.utils.errors import AppError
from app.utils.virtual_clock import get_virtual_now


async def review_request(
    pool: asyncpg.Pool,
    repo: ModuleType,
    request_id: int,
    action: str | None,
    review_note: str | None,
    reviewer: dict,
) -> dict:
    if action not in ("approve", "reject"):
        raise AppError(400, "審核動作僅接受 approve 或 reject。", "VALIDATION_ERROR")
    if action == "reject" and not (review_note and review_note.strip()):
        raise AppError(400, "駁回時必須填寫審核備註。", "VALIDATION_ERROR")

    request = await repo.find_by_id(pool, request_id)
    if not request:
        raise AppError(404, "找不到該申請單。", "NOT_FOUND")
    if request["status"] != "pending":
        raise AppError(409, "該申請單已被審核，無法重複審核。", "ALREADY_REVIEWED")

    # 唯一管理者（admin）沒有代理人可以審核自己送出的申請，故豁免自審限制
    # （見 SPEC.md §3.3）。
    if request["user_id"] == reviewer["id"] and reviewer["role"] != "admin":
        raise AppError(403, "不得審核自己送出的申請。", "FORBIDDEN")
    if reviewer["role"] == "manager" and request["applicant_department_id"] != reviewer["department_id"]:
        raise AppError(403, "僅能審核所屬部門成員的申請。", "FORBIDDEN")

    status = "approved" if action == "approve" else "rejected"
    reviewed_at = await get_virtual_now()
    note = (review_note or "").strip() or None

    updated = await repo.update_review(pool, request_id, status, reviewer["id"], note, reviewed_at)
    if updated is None:
        # 上面的狀態檢查通過後、UPDATE 執行前，被另一個並行請求搶先審核掉了——
        # repo.update_review() 的 WHERE status = 'pending' 是最終防線（見該函式的說明）。
        raise AppError(409, "該申請單已被審核，無法重複審核。", "ALREADY_REVIEWED")
    return dict(updated)
