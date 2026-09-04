"""彈性工時純函式的驗收測試（不打資料庫）。

兩組設定跑同一套規則，確保沒有任何寫死的時間字面值：把設定整組平移後，
到班偏移量、浮動午休、正常工時結束、工時全部要跟著平移（見 SPEC.md §8.2）。
每一列的期望值都是依 SPEC.md §4.1 手算出來的，不是從實作反推。
"""

from datetime import date, datetime, time, timedelta

import pytest

from app.services.leave_hours import compute_leave_hours_for_date
from app.services.work_hours import (
    LATE_PUNCH_OUT_MARGIN,
    OVERTIME_REST,
    WorkSettings,
    calculate_work_hours,
    compute_arrival_offset,
    compute_expected_start,
    compute_normal_work_end,
    compute_overtime_eligible_start,
    compute_work_start,
    daily_work_hours,
    floating_lunch_window,
    format_hours,
    judge_early_leave,
    judge_status,
)

TZ = "Asia/Taipei"
PUNCH_DATE = date(2026, 3, 4)  # 週三

DEFAULT = WorkSettings(
    work_start=time(9, 0), work_end=time(18, 0),
    lunch_start=time(12, 0), lunch_end=time(13, 0), grace_minutes=10,
)
ALT = WorkSettings(
    work_start=time(8, 30), work_end=time(17, 30),
    lunch_start=time(12, 30), lunch_end=time(13, 30), grace_minutes=15,
)


def taipei(hms: str) -> datetime:
    return datetime.fromisoformat(f"{PUNCH_DATE.isoformat()}T{hms}+08:00")


def _case(label, punch_in, punch_out, offset_minutes, work_start, lunch, normal_end, hours, leave=()):
    return {
        "label": label, "punch_in": punch_in, "punch_out": punch_out, "leave": leave,
        "offset_minutes": offset_minutes, "work_start": work_start,
        "lunch": lunch, "normal_end": normal_end, "hours": hours,
    }


# 驗收表 A：預設設定 09:00–18:00／午休 12:00–13:00／緩衝 10 分。
DEFAULT_CASES = [
    _case("晚 5 分到班", "09:05:00", "18:10:00", 5, "09:05:00", ("12:05:00", "13:05:00"), "18:05:00", 8.00),
    _case("遲到超過緩衝，偏移封頂", "09:23:00", "18:23:00", 10, "09:23:00", ("12:10:00", "13:10:00"), "18:10:00", 7.78),
    _case("剛好卡在緩衝上限", "09:10:00", "13:10:00", 10, "09:10:00", ("12:10:00", "13:10:00"), "18:10:00", 3.00),
    _case("提早超過緩衝，起算點被墊高", "08:48:00", "12:48:00", -10, "08:50:00", ("11:50:00", "12:50:00"), "17:50:00", 3.00),
    _case("提早但在緩衝內", "08:55:00", "12:55:00", -5, "08:55:00", ("11:55:00", "12:55:00"), "17:55:00", 3.00),
    _case("午休中到班，不倒給負向偏移", "12:02:00", "18:06:00", 0, "12:02:00", ("12:00:00", "13:00:00"), "18:00:00", 5.00),
    _case("午休後到班，錨點改為午休結束", "13:08:00", "18:08:00", 8, "13:08:00", ("12:08:00", "13:08:00"), "18:08:00", 5.00),
    _case("午休後到班超過緩衝", "13:20:00", "18:20:00", 10, "13:20:00", ("12:10:00", "13:10:00"), "18:10:00", 4.83),
    _case(
        "上午請假，應到班時間推到午休結束", "12:02:00", "18:00:00", 0, "13:00:00",
        ("12:00:00", "13:00:00"), "18:00:00", 5.00, leave=(("09:00:00", "12:00:00"),),
    ),
    _case(
        "下午請假，累積式勝出", "09:02:00", "12:02:00", 2, "09:02:00",
        ("12:02:00", "13:02:00"), "12:02:00", 3.00, leave=(("13:00:00", "18:00:00"),),
    ),
]

# 驗收表 B：非預設設定 08:30–17:30／午休 12:30–13:30／緩衝 15 分。
ALT_CASES = [
    _case("晚 5 分到班", "08:35:00", "17:40:00", 5, "08:35:00", ("12:35:00", "13:35:00"), "17:35:00", 8.00),
    _case("遲到超過緩衝，偏移封頂", "08:53:00", "17:53:00", 15, "08:53:00", ("12:45:00", "13:45:00"), "17:45:00", 7.87),
    _case("剛好卡在緩衝上限", "08:45:00", "13:45:00", 15, "08:45:00", ("12:45:00", "13:45:00"), "17:45:00", 4.00),
    _case("提早超過緩衝，起算點被墊高", "08:12:00", "13:12:00", -15, "08:15:00", ("12:15:00", "13:15:00"), "17:15:00", 4.00),
    _case("提早但在緩衝內", "08:20:00", "13:20:00", -10, "08:20:00", ("12:20:00", "13:20:00"), "17:20:00", 4.00),
    _case("午休中到班，不倒給負向偏移", "12:32:00", "17:36:00", 0, "12:32:00", ("12:30:00", "13:30:00"), "17:30:00", 4.00),
    _case("午休後到班，錨點改為午休結束", "13:38:00", "17:38:00", 8, "13:38:00", ("12:38:00", "13:38:00"), "17:38:00", 4.00),
    _case("午休後到班超過緩衝", "13:55:00", "17:55:00", 15, "13:55:00", ("12:45:00", "13:45:00"), "17:45:00", 3.83),
    _case(
        "上午請假，應到班時間推到午休結束", "12:32:00", "17:30:00", 0, "13:30:00",
        ("12:30:00", "13:30:00"), "17:30:00", 4.00, leave=(("08:30:00", "12:30:00"),),
    ),
    _case(
        "下午請假，累積式勝出", "08:32:00", "12:32:00", 2, "08:32:00",
        ("12:32:00", "13:32:00"), "12:32:00", 4.00, leave=(("13:30:00", "17:30:00"),),
    ),
]

ALL_CASES = [
    pytest.param(DEFAULT, case, id=f"預設-{case['label']}") for case in DEFAULT_CASES
] + [
    pytest.param(ALT, case, id=f"非預設-{case['label']}") for case in ALT_CASES
]


@pytest.mark.parametrize("settings, case", ALL_CASES)
def test_acceptance_row(settings, case):
    punch_in = taipei(case["punch_in"])
    leave_intervals = tuple((taipei(start), taipei(end)) for start, end in case["leave"])

    expected_start = compute_expected_start(PUNCH_DATE, settings, TZ, leave_intervals)
    leave_hours = compute_leave_hours_for_date(PUNCH_DATE, leave_intervals, settings, TZ)

    offset = compute_arrival_offset(punch_in, PUNCH_DATE, settings, TZ, expected_start)
    assert offset == timedelta(minutes=case["offset_minutes"])

    assert compute_work_start(punch_in, PUNCH_DATE, settings, TZ, expected_start) == taipei(case["work_start"])

    assert floating_lunch_window(punch_in, PUNCH_DATE, settings, TZ, expected_start) == (
        taipei(case["lunch"][0]),
        taipei(case["lunch"][1]),
    )

    normal_end = compute_normal_work_end(punch_in, PUNCH_DATE, settings, TZ, expected_start, leave_hours)
    assert normal_end == taipei(case["normal_end"])

    hours = calculate_work_hours(
        punch_in, taipei(case["punch_out"]), PUNCH_DATE, settings, TZ, True, expected_start, leave_hours
    )
    assert hours == case["hours"]


def test_afternoon_leave_leaving_at_normal_end_is_not_early_leave():
    """下午請假做滿扣假後的工時就下班，不算早退（驗收表 A 第 10 列的附加斷言）。"""
    leave = ((taipei("13:00:00"), taipei("18:00:00")),)
    expected_start = compute_expected_start(PUNCH_DATE, DEFAULT, TZ, leave)
    leave_hours = compute_leave_hours_for_date(PUNCH_DATE, leave, DEFAULT, TZ)
    normal_end = compute_normal_work_end(taipei("09:02:00"), PUNCH_DATE, DEFAULT, TZ, expected_start, leave_hours)

    assert judge_early_leave(taipei("12:02:00"), normal_end, workday=True) is False


@pytest.mark.parametrize(
    "settings, on_time, still_on_time, late",
    [
        (DEFAULT, "09:10:00", "09:10:59", "09:11:00"),
        (ALT, "08:45:00", "08:45:59", "08:46:00"),
    ],
)
def test_late_boundary_is_measured_in_minutes_not_seconds(settings, on_time, still_on_time, late):
    """同一個「幾點幾分」不該因為秒數不同判成不同結果（見 docs/PITFALLS.md B2）。"""
    assert judge_status(taipei(on_time), PUNCH_DATE, settings, TZ) == "normal"
    assert judge_status(taipei(still_on_time), PUNCH_DATE, settings, TZ) == "normal"
    assert judge_status(taipei(late), PUNCH_DATE, settings, TZ) == "late"


@pytest.mark.parametrize(
    "settings, punch_in, early, exact",
    [
        (DEFAULT, "09:00:00", "17:59:59", "18:00:00"),
        (ALT, "08:30:00", "17:29:59", "17:30:00"),
    ],
)
def test_early_leave_has_no_grace_at_all(settings, punch_in, early, exact):
    """早退零寬限：差一分鐘就是早退，剛好做滿那一刻不算。"""
    normal_end = compute_normal_work_end(taipei(punch_in), PUNCH_DATE, settings, TZ)

    assert judge_early_leave(taipei(early), normal_end, workday=True) is True
    assert judge_early_leave(taipei(exact), normal_end, workday=True) is False


def test_early_leave_is_false_on_non_workday_and_without_punch_out():
    normal_end = compute_normal_work_end(taipei("09:00:00"), PUNCH_DATE, DEFAULT, TZ)

    assert judge_early_leave(taipei("17:00:00"), normal_end, workday=False) is False
    assert judge_early_leave(None, normal_end, workday=True) is False
    assert judge_early_leave(taipei("17:00:00"), None, workday=True) is False


def test_seconds_are_truncated_before_calculating_hours():
    """09:02:40 上班、12:02:10 下班扣掉秒數後是完整 3.00 小時，不是帶秒相減的 2.99。"""
    assert calculate_work_hours(taipei("09:02:40"), taipei("12:02:10"), PUNCH_DATE, DEFAULT, TZ, True) == 3.00


def test_non_workday_counts_full_time_without_capping():
    """非工作日沒有「正常工時」可封頂，整段扣午休後全額計入（全部待認列為加班）。"""
    hours = calculate_work_hours(taipei("08:00:00"), taipei("20:00:00"), PUNCH_DATE, DEFAULT, TZ, workday=False)

    assert hours == 11.00  # 12 小時扣掉與表定午休重疊的 1 小時


def test_work_hours_is_none_when_either_punch_missing():
    assert calculate_work_hours(taipei("09:00:00"), None, PUNCH_DATE, DEFAULT, TZ, True) is None
    assert calculate_work_hours(None, taipei("18:00:00"), PUNCH_DATE, DEFAULT, TZ, True) is None


@pytest.mark.parametrize(
    "settings, leave, expected",
    [
        (DEFAULT, (), "09:00:00"),
        (DEFAULT, (("09:00:00", "12:00:00"),), "13:00:00"),
        (DEFAULT, (("09:00:00", "10:30:00"),), "10:30:00"),
        (DEFAULT, (("13:00:00", "18:00:00"),), "09:00:00"),
        (DEFAULT, (("09:00:00", "12:30:00"),), "13:00:00"),
        (ALT, (), "08:30:00"),
        (ALT, (("08:30:00", "12:30:00"),), "13:30:00"),
    ],
)
def test_expected_start_skips_leave_from_the_start_of_the_day(settings, leave, expected):
    """只有「從一早就連續涵蓋」的請假會延後應到班時間；中午才開始的假不影響。
    推完後落在表定午休內時再推到午休結束——半天假下午回來本來就有一段午休銜接。
    """
    intervals = tuple((taipei(start), taipei(end)) for start, end in leave)

    assert compute_expected_start(PUNCH_DATE, settings, TZ, intervals) == taipei(expected)


def test_overtime_eligible_start_rests_30_minutes_after_normal_end_on_workday():
    normal_end = compute_normal_work_end(taipei("09:00:00"), PUNCH_DATE, DEFAULT, TZ)
    eligible = compute_overtime_eligible_start(taipei("09:00:00"), PUNCH_DATE, DEFAULT, TZ, workday=True)

    assert eligible == normal_end + OVERTIME_REST
    assert eligible == taipei("18:30:00")


def test_overtime_eligible_start_on_non_workday_is_punch_in_truncated_to_minute():
    """假日 08:56:37 打卡後申請 08:56 開始的加班，不該被自己的防呆擋下。"""
    eligible = compute_overtime_eligible_start(taipei("08:56:37"), PUNCH_DATE, DEFAULT, TZ, workday=False)

    assert eligible == taipei("08:56:00")


def test_late_punch_out_threshold_is_one_hour_after_normal_end():
    normal_end = compute_normal_work_end(taipei("09:00:00"), PUNCH_DATE, DEFAULT, TZ)

    assert normal_end + LATE_PUNCH_OUT_MARGIN == taipei("19:00:00")


@pytest.mark.parametrize("settings", [DEFAULT, ALT])
def test_daily_work_hours_excludes_lunch(settings):
    assert daily_work_hours(settings) == 8.0


def test_format_hours_keeps_two_decimal_places():
    assert format_hours(8.0) == "8.00"
    assert format_hours(7.78) == "7.78"
    assert format_hours(None) is None
