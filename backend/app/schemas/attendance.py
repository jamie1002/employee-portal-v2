"""出勤查詢的請求驗證。"""

from app.schemas.common import (
    parse_date_str,
    parse_int_in_range,
    parse_optional_date_str,
    parse_optional_positive_int,
    validation_error,
)

# 狀態篩選比對的是**生效值**（見 services/attendance_effective.py）。除了
# attendances.status 本身的列舉值，另加兩個讀取時才衍生出來的判定：
# early_leave（早退）與 missing_punch_out（忘記打下班卡），原始欄位沒有對應值。
VALID_STATUS_FILTERS = {
    "normal", "late", "absent", "holiday_work", "on_leave", "early_leave", "missing_punch_out",
}


def _parse_optional_status(params: dict) -> str | None:
    status = params.get("status")
    if status is None or status == "":
        return None
    if status not in VALID_STATUS_FILTERS:
        raise validation_error(f"status 必須為 {'、'.join(sorted(VALID_STATUS_FILTERS))} 其中之一")
    return status


def parse_my_attendance_query(params: dict) -> dict:
    return {
        "start_date": parse_optional_date_str(params, "start_date"),
        "end_date": parse_optional_date_str(params, "end_date"),
        "status": _parse_optional_status(params),
        "page": parse_int_in_range(params.get("page"), "page", default=1, minimum=1, maximum=100_000),
        "page_size": parse_int_in_range(params.get("page_size"), "page_size", default=20, minimum=1, maximum=100),
    }


def parse_company_attendance_query(params: dict) -> dict:
    return {
        "user_id": parse_optional_positive_int(params.get("user_id"), "user_id 格式不正確"),
        "department_id": parse_optional_positive_int(params.get("department_id"), "department_id 格式不正確"),
        "start_date": parse_optional_date_str(params, "start_date"),
        "end_date": parse_optional_date_str(params, "end_date"),
        "status": _parse_optional_status(params),
    }


def parse_attendance_changes_query(params: dict) -> dict:
    start_date = parse_date_str(params, "start_date")
    end_date = parse_date_str(params, "end_date")
    if end_date < start_date:
        raise validation_error("end_date 不得早於 start_date")
    return {
        "start_date": start_date,
        "end_date": end_date,
        "user_id": parse_optional_positive_int(params.get("user_id"), "user_id 格式不正確"),
        "department_id": parse_optional_positive_int(params.get("department_id"), "department_id 格式不正確"),
    }
