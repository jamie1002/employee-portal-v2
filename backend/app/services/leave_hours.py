"""請假時數的純函式。

與出勤工時（work_hours.py）刻意不同的兩點，都是規則本身的差異、不是不一致：

1. **請假的午休固定不浮動**：請假通常事前申請，當天沒有打卡時間可據以浮動，
   硬要浮動只會讓基準比規則本身更難解釋。
2. **緩衝只套用在整段請假區間真正的頭尾兩端**：多天請假的中間日、以及非頭尾
   那一側，一律用未緩衝的表定時間。否則「週五 09:00 到週一 18:00」這種剛好卡
   整點的多天請假，會因為兩端各自誤套緩衝而多算 20 分鐘（16.00 變成 16.33）。
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.work_hours import WorkSettings, at


def _local_date(moment: datetime, tz: str) -> date:
    return moment.astimezone(ZoneInfo(tz)).date()


def calculate_leave_hours_by_day(
    start_time: datetime,
    end_time: datetime,
    settings: WorkSettings,
    tz: str,
    holiday_dates: set[date] | None = None,
) -> dict[date, float]:
    """把請假區間依台北時區逐日切分，跳過週末與國定假日，回傳 {日期: 當日時數}。

    每個工作日的「工作時間窗」切成 `[work_start − grace, lunch_start]` 與
    `[lunch_end, work_end + grace]` 兩段分別取交集後相加——不是拿整段
    work_start~work_end 直接相減，那會把午休也算成請假時數。

    刻意不在這裡四捨五入：呼叫端要先加總原始值再一次四捨五入，逐日先各自
    進位再加總會累積誤差。
    """
    holiday_dates = holiday_dates or set()

    first_day = _local_date(start_time, tz)
    last_day = _local_date(end_time, tz)

    by_day: dict[date, float] = {}
    cursor = first_day

    while cursor <= last_day:
        if cursor.weekday() < 5 and cursor not in holiday_dates:
            start_grace = settings.grace if cursor == first_day else timedelta(0)
            end_grace = settings.grace if cursor == last_day else timedelta(0)

            day_work_start = at(cursor, settings.work_start, tz) - start_grace
            day_work_end = at(cursor, settings.work_end, tz) + end_grace
            day_lunch_start = at(cursor, settings.lunch_start, tz)
            day_lunch_end = at(cursor, settings.lunch_end, tz)

            day_total = timedelta(0)
            for segment_start, segment_end in (
                (day_work_start, day_lunch_start),
                (day_lunch_end, day_work_end),
            ):
                lo = max(start_time, segment_start)
                hi = min(end_time, segment_end)
                if hi > lo:
                    day_total += hi - lo

            if day_total > timedelta(0):
                by_day[cursor] = day_total.total_seconds() / 3600

        cursor += timedelta(days=1)

    return by_day


def compute_leave_hours_for_date(
    punch_date: date,
    leave_intervals,
    settings: WorkSettings,
    tz: str,
) -> float:
    """加總當日所有已核准請假區間與表定工時的交集時數。

    沿用 calculate_leave_hours_by_day() 的逐日交集邏輯，確保出勤這一側算出的
    「當日已請假時數」與請假申請單自己算出的時數規則永遠同步。
    呼叫端已保證 punch_date 是工作日，故這裡不需要再傳 holiday_dates。
    """
    total = 0.0
    for start, end in leave_intervals:
        by_day = calculate_leave_hours_by_day(start, end, settings, tz, holiday_dates=set())
        total += by_day.get(punch_date, 0.0)
    return total
