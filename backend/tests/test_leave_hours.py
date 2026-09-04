"""請假時數與加班時數純函式測試（不打資料庫）。"""

from datetime import datetime, time

from app.services.leave_hours import calculate_leave_hours, calculate_overtime_hours
from app.services.work_hours import WorkSettings

SETTINGS = WorkSettings(
    work_start=time(9, 0), work_end=time(18, 0),
    lunch_start=time(12, 0), lunch_end=time(13, 0), grace_minutes=10,
)
TZ = "Asia/Taipei"


def taipei(date_time: str) -> datetime:
    return datetime.fromisoformat(f"{date_time}+08:00")


def test_single_workday_full_span_excludes_lunch():
    hours = calculate_leave_hours(taipei("2026-08-24T09:00:00"), taipei("2026-08-24T18:00:00"), SETTINGS, TZ)
    assert hours == 8.0


def test_single_workday_partial_after_lunch():
    hours = calculate_leave_hours(taipei("2026-08-24T13:00:00"), taipei("2026-08-24T17:00:00"), SETTINGS, TZ)
    assert hours == 4.0


def test_partial_span_overlapping_lunch():
    # 11:00–14:00 跨越午休：[11:00,12:00) 1h + [13:00,14:00) 1h = 2 小時。
    hours = calculate_leave_hours(taipei("2026-08-24T11:00:00"), taipei("2026-08-24T14:00:00"), SETTINGS, TZ)
    assert hours == 2.0


def test_friday_to_monday_excludes_weekend():
    hours = calculate_leave_hours(taipei("2026-08-28T09:00:00"), taipei("2026-08-31T18:00:00"), SETTINGS, TZ)
    assert hours == 16.0


def test_window_extended_by_grace_buffer_at_head_and_tail():
    """實測回報：08:56–11:56 應為完整 3.00 小時（落在緩衝後的窗口 08:50–12:00 內）。"""
    hours = calculate_leave_hours(taipei("2026-08-24T08:56:00"), taipei("2026-08-24T11:56:00"), SETTINGS, TZ)
    assert hours == 3.0


def test_before_grace_buffer_not_counted():
    hours = calculate_leave_hours(taipei("2026-08-24T08:40:00"), taipei("2026-08-24T08:50:00"), SETTINGS, TZ)
    assert hours == 0.0


def test_middle_day_of_multi_day_leave_does_not_get_grace_buffer():
    """多天請假只有整段區間真正的頭尾兩端套用緩衝，中間日一律用未緩衝的表定時間。

    週一 08:50（頭）→ 週三 18:10（尾），跨三個工作日：週一、週三各因緩衝多得
    10 分鐘（8h10m），中間的週二完全沒有緩衝（整整 8h）——總計 24.33 小時，
    不是「三天都套緩衝」的 24.67，也不是「完全不套緩衝」的 24.00。
    """
    hours = calculate_leave_hours(taipei("2026-08-24T08:50:00"), taipei("2026-08-26T18:10:00"), SETTINGS, TZ)
    assert hours == 24.33


def test_pure_weekend_span_is_zero():
    hours = calculate_leave_hours(taipei("2026-08-29T09:00:00"), taipei("2026-08-30T18:00:00"), SETTINGS, TZ)
    assert hours == 0.0


def test_holiday_dates_are_excluded():
    from datetime import date

    hours = calculate_leave_hours(
        taipei("2026-08-27T09:00:00"), taipei("2026-08-27T18:00:00"), SETTINGS, TZ,
        holiday_dates={date(2026, 8, 27)},
    )
    assert hours == 0.0


def test_overtime_does_not_exclude_weekend():
    hours = calculate_overtime_hours(taipei("2026-08-29T13:00:00"), taipei("2026-08-29T17:00:00"), SETTINGS, TZ)
    assert hours == 4.0


def test_overtime_deducts_lunch_overlap():
    hours = calculate_overtime_hours(taipei("2026-08-29T09:00:00"), taipei("2026-08-29T13:00:00"), SETTINGS, TZ)
    assert hours == 3.0


def test_overtime_half_hour_boundary():
    hours = calculate_overtime_hours(taipei("2026-08-24T18:00:00"), taipei("2026-08-24T18:30:00"), SETTINGS, TZ)
    assert hours == 0.5


def test_overtime_below_half_hour_floors_to_zero():
    hours = calculate_overtime_hours(taipei("2026-08-24T18:00:00"), taipei("2026-08-24T18:12:00"), SETTINGS, TZ)
    assert hours == 0.0
