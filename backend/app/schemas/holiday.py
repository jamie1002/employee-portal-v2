"""國定假日的手刻請求驗證（SPEC.md §4.9）。"""

from app.schemas.common import parse_date_str, require_str


def parse_create_holiday(data: dict) -> dict:
    holiday_date = parse_date_str(data, "holiday_date")
    name = require_str(data, "name", "請輸入假日名稱")
    return {"holiday_date": holiday_date, "name": name}
