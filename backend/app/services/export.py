"""匯出報表的業務邏輯（SPEC.md §4.8）。

範圍限縮一律 **deny-by-default**：判斷式寫「不是 admin 就限縮部門」，不要寫
「是 manager 才限縮」——後者一旦出現第四種可匯出身分（被授予 `exports.run`
的一般員工）就會直接落進不限縮分支（見 docs/PITFALLS.md C1）。`room-bookings`
是唯一的例外，不受此限縮。
"""

import io
from datetime import date, datetime
from zoneinfo import ZoneInfo

import asyncpg
from openpyxl import Workbook

from app.config.settings import app_settings
from app.repositories import attendance_repository, room_booking_repository, user_repository
from app.schemas.export import EXPORT_COLUMNS
from app.services import attendance_effective
from app.utils.errors import AppError
from app.utils.timezone import get_business_date
from app.utils.virtual_clock import get_virtual_now

_EARLIEST_DATE = date(2000, 1, 1)
_TZ = ZoneInfo(app_settings.APP_TIMEZONE)

_ROLE_LABEL = {"admin": "系統管理者", "manager": "部門主管", "employee": "一般員工"}
_ATTENDANCE_STATUS_LABEL = {
    "normal": "正常", "late": "遲到", "absent": "缺勤", "holiday_work": "假日出勤", "on_leave": "請假",
}
_REVIEW_STATUS_LABEL = {"pending": "待審", "approved": "已核准", "rejected": "已駁回"}
_PUNCH_TYPE_LABEL = {"in": "補上班卡", "out": "補下班卡", "both": "補上下班卡"}
_BOOKING_STATUS_LABEL = {"confirmed": "已確認", "cancelled": "已取消"}


async def _scope_filters(kind: str, filters: dict, requester: dict, pool: asyncpg.Pool) -> dict:
    if kind == "room-bookings" or requester["role"] == "admin":
        return filters

    scope_department_id = requester["department_id"]
    if scope_department_id is None:
        raise AppError(403, "尚未指派所屬部門，無法匯出資料。", "FORBIDDEN")

    if filters.get("user_id") is not None:
        target = await user_repository.find_public_by_id(pool, filters["user_id"])
        if not target or target["department_id"] != scope_department_id:
            raise AppError(403, "僅能匯出所屬部門成員的資料。", "FORBIDDEN")

    # 強制覆蓋成請求者自己的部門，不理會前端傳來的 department_id。
    return {**filters, "department_id": scope_department_id}


async def _resolve_attendance_user_ids(pool: asyncpg.Pool, filters: dict) -> list[int]:
    if filters.get("user_id") is not None:
        return [filters["user_id"]]
    members = await user_repository.find_all(pool, department_id=filters.get("department_id"))
    return [member["id"] for member in members]


def _date_range(filters: dict, today: date) -> tuple[date, date]:
    start_date = filters.get("start_date") or _EARLIEST_DATE
    end_date = filters.get("end_date") or today
    return start_date, end_date


def _format_taipei(moment: datetime) -> str:
    return moment.astimezone(_TZ).strftime("%H:%M")


def _project_change_row(row: dict) -> dict:
    if row["source"] == "punch_request":
        request_type = _PUNCH_TYPE_LABEL.get(row["punch_type"], "補打卡")
        period = str(row["start_date"])
        parts = []
        if row["requested_in_time"]:
            parts.append(f"上班 {_format_taipei(row['requested_in_time'])}")
        if row["requested_out_time"]:
            parts.append(f"下班 {_format_taipei(row['requested_out_time'])}")
        detail = "、".join(parts) if parts else (row["reason"] or "")
    else:
        request_type = f"請假（{row['leave_type']}）"
        period = f"{row['start_date']} ~ {row['end_date']}"
        detail = f"{row['hours']} 小時" if row["hours"] is not None else (row["reason"] or "")

    return {
        "employee_no": row["employee_no"],
        "user_name": row["user_name"],
        "department_name": row["department_name"],
        "request_type": request_type,
        "period": period,
        "detail": detail,
        "status": _REVIEW_STATUS_LABEL.get(row["status"], row["status"]),
        "submitted_at": row["submitted_at"],
        "reviewer_name": row["reviewer_name"],
        "reviewed_at": row["reviewed_at"],
        "review_note": row["review_note"],
    }


async def _fetch_attendance_raw(pool: asyncpg.Pool, user_ids: list[int], start_date: date, end_date: date) -> list[dict]:
    raw_rows = await attendance_repository.find_by_users_in_range(pool, user_ids, start_date, end_date)
    users_by_id = {user["id"]: user for user in await user_repository.find_by_ids(pool, user_ids)}

    rows = []
    for row in raw_rows:
        user = users_by_id.get(row["user_id"])
        if user is None:
            continue
        merged = dict(row)
        merged["employee_no"] = user["employee_no"]
        merged["user_name"] = user["name"]
        merged["department_name"] = user["department_name"]
        merged["status"] = _ATTENDANCE_STATUS_LABEL.get(merged["status"], merged["status"])
        rows.append(merged)

    rows.sort(key=lambda r: (r["punch_date"], r.get("user_name") or ""), reverse=True)
    return rows


async def _fetch_rows(pool: asyncpg.Pool, kind: str, filters: dict) -> list[dict]:
    if kind == "employees":
        rows = [dict(row) for row in await user_repository.find_all(pool, department_id=filters.get("department_id"))]
        for row in rows:
            row["role"] = _ROLE_LABEL.get(row["role"], row["role"])
        return rows

    if kind in ("attendance", "attendance-raw", "attendance-changes"):
        user_ids = await _resolve_attendance_user_ids(pool, filters)
        if not user_ids:
            return []
        virtual_now = await get_virtual_now()
        today = get_business_date(virtual_now, app_settings.APP_TIMEZONE)
        start_date, end_date = _date_range(filters, today)

        if kind == "attendance":
            rows = await attendance_effective.resolve_range(pool, user_ids, start_date, end_date)
            for row in rows:
                row["effective_status"] = _ATTENDANCE_STATUS_LABEL.get(row["effective_status"], row["effective_status"])
            return rows

        if kind == "attendance-raw":
            return await _fetch_attendance_raw(pool, user_ids, start_date, end_date)

        raw = await attendance_repository.find_changes(pool, user_ids, start_date, end_date, app_settings.APP_TIMEZONE)
        return [_project_change_row(dict(row)) for row in raw]

    # room-bookings
    rows = [
        dict(row)
        for row in await room_booking_repository.find_all_in_range(
            pool, filters.get("start_date"), filters.get("end_date"), filters.get("room_id"), filters.get("department_id")
        )
    ]
    for row in rows:
        row["status"] = _BOOKING_STATUS_LABEL.get(row["status"], row["status"])
    return rows


def _to_cell_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return value


def _project(rows: list[dict], columns: list[str]) -> list[list]:
    return [[_to_cell_value(row.get(key)) for key in columns] for row in rows]


async def get_export_preview(pool: asyncpg.Pool, kind: str, filters: dict, columns: list[str], requester: dict) -> dict:
    scoped_filters = await _scope_filters(kind, filters, requester, pool)
    rows = await _fetch_rows(pool, kind, scoped_filters)
    labels = dict(EXPORT_COLUMNS[kind])
    projected = _project(rows, columns)
    return {
        "columns": [{"key": key, "label": labels[key]} for key in columns],
        "rows": projected,
        "total": len(projected),
    }


async def build_export_xlsx(pool: asyncpg.Pool, kind: str, filters: dict, columns: list[str], requester: dict) -> bytes:
    preview = await get_export_preview(pool, kind, filters, columns, requester)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = kind[:31]  # Excel 工作表名稱上限 31 字元
    sheet.append([column["label"] for column in preview["columns"]])
    for row in preview["rows"]:
        sheet.append(row)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
