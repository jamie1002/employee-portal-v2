"""場地預約的業務邏輯（SPEC.md §4.6）。

兩層防護：這裡的 `find_conflicts` 預檢只負責擋下多數情況、並產出含衝突時段與
預約人姓名的友善訊息；真正保證正確性的是 INSERT 時資料庫的 `no_double_booking`
排除約束——兩個並行請求都可能通過預檢（此時都還沒 INSERT），最終只有一筆
INSERT 會成功，另一筆由 `ExclusionViolationError` 轉譯成 409（見
middleware/error_handler.py）。這是刻意的 TOCTOU 對策，不是漏洞。
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import asyncpg

from app.repositories import room_booking_repository, room_repository
from app.utils.errors import AppError


def _format_hhmm(moment: datetime, tz: str) -> str:
    return moment.astimezone(ZoneInfo(tz)).strftime("%H:%M")


async def _conflict_message(
    pool: asyncpg.Pool, room_id: int, start_time: datetime, end_time: datetime, tz: str
) -> str | None:
    conflicts = await room_booking_repository.find_conflicts(pool, room_id, start_time, end_time)
    if not conflicts:
        return None
    first = conflicts[0]
    return (
        f"此時段與既有預約衝突：{_format_hhmm(first['start_time'], tz)}"
        f"–{_format_hhmm(first['end_time'], tz)}（{first['booked_by_name']}）"
    )


async def create_booking(
    pool: asyncpg.Pool, user_id: int, room_id: int, title: str, start_time: datetime, end_time: datetime, tz: str
) -> dict:
    room = await room_repository.find_by_id(pool, room_id)
    if room is None:
        raise AppError(404, "找不到指定的場地。", "NOT_FOUND")

    message = await _conflict_message(pool, room_id, start_time, end_time, tz)
    if message:
        raise AppError(409, message, "BOOKING_CONFLICT")

    booking = await room_booking_repository.create(pool, user_id, room_id, title, start_time, end_time)
    return dict(booking)


async def list_bookings(
    pool: asyncpg.Pool, target_date: date, room_id: int | None = None, status: str | None = None
) -> list[dict]:
    rows = await room_booking_repository.find_by_date(pool, target_date, room_id, status)
    return [dict(row) for row in rows]


async def cancel_booking(pool: asyncpg.Pool, booking_id: int, actor: dict) -> dict:
    """僅本人可取消自己的預約；admin 不受此限（SPEC.md §4.6，與強制釋放是兩件事：
    這裡仍是軟取消，DELETE 端點才是 admin 專用的強制釋放）。"""
    booking = await room_booking_repository.find_by_id(pool, booking_id)
    if booking is None:
        raise AppError(404, "找不到該預約。", "NOT_FOUND")
    if booking["user_id"] != actor["id"] and actor["role"] != "admin":
        raise AppError(403, "僅能取消自己的預約。", "FORBIDDEN")
    if booking["status"] == "cancelled":
        raise AppError(409, "該預約已被取消。", "ALREADY_CANCELLED")

    updated = await room_booking_repository.cancel_by_id(pool, booking_id)
    if updated is None:
        raise AppError(409, "該預約已被取消。", "ALREADY_CANCELLED")
    return dict(updated)


async def force_release(pool: asyncpg.Pool, booking_id: int) -> None:
    """admin 專用：這筆預約不該存在，直接刪除，語意與「取消」（軟刪除）不同。"""
    deleted = await room_booking_repository.delete_by_id(pool, booking_id)
    if deleted is None:
        raise AppError(404, "找不到該預約。", "NOT_FOUND")
