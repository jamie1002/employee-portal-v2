"""考勤設定的手刻請求驗證（SPEC.md §6.6）。"""

import re
from datetime import time

from app.schemas.common import validation_error

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _parse_time_field(data: dict, key: str) -> time:
    raw = data.get(key)
    if not isinstance(raw, str) or not _TIME_RE.match(raw):
        raise validation_error(f"{key} 必須是 HH:mm 格式")
    return time.fromisoformat(raw)


def parse_update_settings(data: dict) -> dict:
    work_start = _parse_time_field(data, "work_start_time")
    work_end = _parse_time_field(data, "work_end_time")
    lunch_start = _parse_time_field(data, "lunch_start_time")
    lunch_end = _parse_time_field(data, "lunch_end_time")

    grace_period_minutes = data.get("grace_period_minutes")
    if not isinstance(grace_period_minutes, int) or isinstance(grace_period_minutes, bool):
        raise validation_error("grace_period_minutes 必須是整數")
    if grace_period_minutes < 0 or grace_period_minutes > 240:
        raise validation_error("grace_period_minutes 必須介於 0 到 240 之間")

    if not (work_start < lunch_start < lunch_end < work_end):
        raise validation_error("考勤時段設定不合理，須符合「上班 < 午休開始 < 午休結束 < 下班」")

    return {
        "work_start_time": work_start,
        "work_end_time": work_end,
        "lunch_start_time": lunch_start,
        "lunch_end_time": lunch_end,
        "grace_period_minutes": grace_period_minutes,
    }
