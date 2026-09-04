"""場地預約的手刻請求驗證（SPEC.md §4.6）。"""

from app.schemas.common import (
    parse_date_str,
    parse_datetime_field,
    parse_optional_positive_int,
    require_str,
    validation_error,
)
from app.utils.timezone import get_business_date

_STATUS_VALUES = ("confirmed", "cancelled")


def parse_create_room_booking(data: dict, tz: str) -> dict:
    room_id = parse_optional_positive_int(data.get("room_id"), "請選擇場地")
    if room_id is None:
        raise validation_error("請選擇場地")
    title = require_str(data, "title", "請輸入預約標題")
    start_time = parse_datetime_field(data, "start_time")
    end_time = parse_datetime_field(data, "end_time")

    if end_time <= start_time:
        raise validation_error("結束時間必須晚於開始時間")
    if get_business_date(start_time, tz) != get_business_date(end_time, tz):
        raise validation_error("單筆預約不得跨日")

    return {"room_id": room_id, "title": title, "start_time": start_time, "end_time": end_time}


def parse_room_booking_query(params: dict) -> dict:
    target_date = parse_date_str(params, "date")
    room_id = parse_optional_positive_int(params.get("room_id"), "room_id 格式不正確")
    status = params.get("status") or None
    if status is not None and status not in _STATUS_VALUES:
        raise validation_error("status 必須是 confirmed 或 cancelled")
    return {"date": target_date, "room_id": room_id, "status": status}
