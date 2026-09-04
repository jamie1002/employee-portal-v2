"""申請單的請求驗證：補打卡／請假／加班（SPEC.md §4.3 §4.4 §4.5）。"""

from datetime import date, datetime

from app.schemas.common import (
    parse_datetime_field,
    parse_optional_datetime_field,
    require_str,
    validation_error,
)
from app.utils.timezone import get_business_date

LEAVE_TYPES = ("事假", "病假", "特別休假", "公假")
PUNCH_TYPES = ("in", "out", "both")

# 特別休假（年假）是員工自己的權益假別，不強制填理由；其餘假別仍為必填。
OPTIONAL_REASON_LEAVE_TYPE = "特別休假"


def parse_create_punch_request(data: dict, now: datetime, tz: str) -> dict:
    """`now` 由呼叫端傳入 get_virtual_now() 的結果，「不得為未來日期」的判斷才會
    跟著虛擬時鐘走，不是抓真實系統時間（見 CLAUDE.md 硬性規則）。"""
    punch_type = data.get("type")
    if punch_type not in PUNCH_TYPES:
        raise validation_error("type 必須為 in、out 或 both")

    target_date_raw = data.get("target_date")
    if not isinstance(target_date_raw, str) or not target_date_raw:
        raise validation_error("target_date 為必填")
    try:
        target_date = date.fromisoformat(target_date_raw)
    except ValueError:
        raise validation_error("target_date 格式不正確，須為 YYYY-MM-DD") from None

    requested_in_time = parse_optional_datetime_field(data, "requested_in_time")
    requested_out_time = parse_optional_datetime_field(data, "requested_out_time")
    reason = require_str(data, "reason", "請填寫申請理由")

    if punch_type == "in" and not requested_in_time:
        raise validation_error("補上班卡必須提供 requested_in_time")
    if punch_type == "out" and not requested_out_time:
        raise validation_error("補下班卡必須提供 requested_out_time")
    if punch_type == "both":
        if not (requested_in_time and requested_out_time):
            raise validation_error("同時補上下班卡須提供 requested_in_time 與 requested_out_time")
        if requested_out_time <= requested_in_time:
            raise validation_error("下班時間必須晚於上班時間")

    if target_date > get_business_date(now, tz=tz):
        raise validation_error("補打卡日期不得為未來日期")

    return {
        "type": punch_type,
        "target_date": target_date,
        "requested_in_time": requested_in_time,
        "requested_out_time": requested_out_time,
        "reason": reason,
    }


def parse_create_leave_request(data: dict) -> dict:
    leave_type = data.get("leave_type")
    if leave_type not in LEAVE_TYPES:
        raise validation_error(f"leave_type 必須為 {'、'.join(LEAVE_TYPES)} 其中之一")

    start_time = parse_datetime_field(data, "start_time")
    end_time = parse_datetime_field(data, "end_time")

    if leave_type == OPTIONAL_REASON_LEAVE_TYPE:
        reason_raw = data.get("reason")
        reason = reason_raw.strip() if isinstance(reason_raw, str) else ""
    else:
        reason = require_str(data, "reason", "請填寫申請理由")

    if end_time <= start_time:
        raise validation_error("結束時間必須晚於開始時間")

    return {"leave_type": leave_type, "start_time": start_time, "end_time": end_time, "reason": reason}


def parse_create_overtime_request(data: dict) -> dict:
    """不限制輸入時間須對齊整點／半點——時數改在 calculate_overtime_hours() 以
    30 分鐘為單位無條件捨去，不足 30 分鐘的部分不計入（見 SPEC.md §4.4）。"""
    start_time = parse_datetime_field(data, "start_time")
    end_time = parse_datetime_field(data, "end_time")
    reason = require_str(data, "reason", "請填寫加班事由")

    if end_time <= start_time:
        raise validation_error("結束時間必須晚於開始時間")

    return {"start_time": start_time, "end_time": end_time, "reason": reason}


def parse_request_query(params: dict) -> dict:
    status = params.get("status")
    if status is not None and status not in ("pending", "approved", "rejected"):
        raise validation_error("status 必須為 pending、approved 或 rejected")
    return {"status": status}
