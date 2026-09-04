"""匯出報表的手刻請求驗證（SPEC.md §4.8）。"""

from app.schemas.common import parse_optional_date_str, parse_optional_positive_int, validation_error

EXPORT_KINDS = ("employees", "attendance", "attendance-raw", "attendance-changes", "room-bookings")

# 三種出勤類匯出共用「員工」篩選與日期區間；room-bookings 不受部門範圍限縮
# （SPEC.md §4.8），欄位另外用 room_id 篩選。
ATTENDANCE_LIKE_KINDS = ("attendance", "attendance-raw", "attendance-changes")

# 每個匯出類型允許的欄位，(欄位鍵, 中文表頭)，順序即匯出欄位順序。
EXPORT_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "employees": [
        ("employee_no", "員工編號"),
        ("name", "姓名"),
        ("email", "電子郵件"),
        ("role", "職位"),
        ("department_name", "部門"),
        ("extension_number", "分機"),
        ("hire_date", "到職日"),
    ],
    "attendance": [
        ("employee_no", "員工編號"),
        ("user_name", "姓名"),
        ("department_name", "部門"),
        ("punch_date", "日期"),
        ("effective_punch_in_time", "上班時間"),
        ("effective_punch_out_time", "下班時間"),
        ("effective_status", "狀態"),
        ("effective_work_hours", "工時"),
        ("effective_is_early_leave", "早退"),
        ("is_missing_punch_out", "未打下班卡"),
        ("is_adjusted", "已異動"),
        ("note", "備註"),
    ],
    "attendance-raw": [
        ("employee_no", "員工編號"),
        ("user_name", "姓名"),
        ("department_name", "部門"),
        ("punch_date", "日期"),
        ("punch_in_time", "上班時間"),
        ("punch_out_time", "下班時間"),
        ("status", "狀態"),
        ("work_hours", "工時"),
        ("is_early_leave", "早退"),
        ("note", "備註"),
    ],
    "attendance-changes": [
        ("employee_no", "員工編號"),
        ("user_name", "姓名"),
        ("department_name", "部門"),
        ("request_type", "申請類型"),
        ("period", "期間"),
        ("detail", "內容"),
        ("status", "狀態"),
        ("submitted_at", "申請時間"),
        ("reviewer_name", "審核人"),
        ("reviewed_at", "審核時間"),
        ("review_note", "審核意見"),
    ],
    "room-bookings": [
        ("room_name", "場地"),
        ("booked_by_name", "預約人"),
        ("department_name", "部門"),
        ("title", "標題"),
        ("start_time", "開始時間"),
        ("end_time", "結束時間"),
        ("status", "狀態"),
    ],
}


def parse_export_kind(kind: str) -> str:
    if kind not in EXPORT_KINDS:
        raise validation_error("不支援的匯出類型。")
    return kind


def parse_export_request(kind: str, data: dict) -> dict:
    body_filters = data.get("filters") or {}
    if not isinstance(body_filters, dict):
        raise validation_error("filters 必須是物件。")

    filters = {
        "department_id": parse_optional_positive_int(body_filters.get("department_id"), "department_id 格式不正確"),
        "start_date": parse_optional_date_str(body_filters, "start_date"),
        "end_date": parse_optional_date_str(body_filters, "end_date"),
    }
    if kind in ATTENDANCE_LIKE_KINDS:
        filters["user_id"] = parse_optional_positive_int(body_filters.get("user_id"), "user_id 格式不正確")
    if kind == "room-bookings":
        filters["room_id"] = parse_optional_positive_int(body_filters.get("room_id"), "room_id 格式不正確")

    columns = data.get("columns")
    if columns is None:
        columns = [key for key, _ in EXPORT_COLUMNS[kind]]
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        raise validation_error("columns 必須是字串陣列。")

    valid_keys = {key for key, _ in EXPORT_COLUMNS[kind]}
    invalid = [c for c in columns if c not in valid_keys]
    if invalid:
        raise validation_error(f"不支援的欄位：{', '.join(invalid)}。")

    return {"filters": filters, "columns": columns}
