"""彈性工時的純函式：不碰 I/O，可單獨單元測試（見 CLAUDE.md 分層紀律）。

這裡是整個系統最容易算錯的地方，規則的完整推導見 SPEC.md §4.1，驗收用的
邊界案例表見 docs/REBUILD-TASKS.md 批 2。幾個一再踩到的原則：

- **禁止寫死時間字面值**：09:00／18:00／12:00／10 分鐘等一律來自 `WorkSettings`
  （亦即 `system_settings`），把設定整組平移後所有規則都要跟著平移。
- **一律先截斷到分鐘再比較**：在每個接受時間參數的函式入口就截斷，不依賴呼叫端。
  否則同一個「9 點 10 分」會因為秒數不同判成不同結果（見 docs/PITFALLS.md B2）。
- **到班偏移量是唯一的偏移來源**：正常工時結束、浮動午休、工時起算點三者共用它，
  不各自算一套。
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.utils.timezone import truncate_to_minute

# 以下兩個是法規／產品常數，刻意不放進 system_settings：
# OVERTIME_REST 是「加班與正常工時之間必須間隔的休息時間」，屬於勞動法規層級的
# 規則，不是管理者可自由調整的考勤設定；LATE_PUNCH_OUT_MARGIN 只影響「要不要跳出
# 晚下班提示」這個產品決策，完全不參與計薪，沒有必要開放設定。
OVERTIME_REST = timedelta(minutes=30)
LATE_PUNCH_OUT_MARGIN = timedelta(hours=1)


@dataclass(frozen=True)
class WorkSettings:
    """考勤設定的純資料表示，讓純函式不必依賴資料庫列的形狀。"""

    work_start: time
    work_end: time
    lunch_start: time
    lunch_end: time
    grace_minutes: int

    @classmethod
    def from_row(cls, row) -> "WorkSettings":
        return cls(
            work_start=row["work_start_time"],
            work_end=row["work_end_time"],
            lunch_start=row["lunch_start_time"],
            lunch_end=row["lunch_end_time"],
            grace_minutes=row["grace_period_minutes"],
        )

    @property
    def grace(self) -> timedelta:
        return timedelta(minutes=self.grace_minutes)

    @property
    def lunch_duration(self) -> timedelta:
        return _time_to_delta(self.lunch_end) - _time_to_delta(self.lunch_start)

    @property
    def scheduled_duration(self) -> timedelta:
        return _time_to_delta(self.work_end) - _time_to_delta(self.work_start)


def _time_to_delta(value: time) -> timedelta:
    return timedelta(hours=value.hour, minutes=value.minute, seconds=value.second)


def at(punch_date: date, value: time, tz: str) -> datetime:
    """把「某營業日的某個時刻」換算成 UTC 時間點（時刻本身以台北時區解讀）。"""
    local = datetime.combine(punch_date, value.replace(second=0, microsecond=0), tzinfo=ZoneInfo(tz))
    return local.astimezone(timezone.utc)


def format_hours(hours: float | None) -> str | None:
    """工時一律以兩位小數的字串對外呈現。

    資料庫的 NUMERIC(5,2) 經 asyncpg codec 解碼本來就是 "8.00" 這種字串，
    讀取時即時算出的生效工時若回傳 float，同一個欄位在畫面上會時而 `8.00`
    時而 `8`。統一在這裡格式化，API 契約與畫面才一致。
    """
    return None if hours is None else f"{hours:.2f}"


def compute_expected_start(
    punch_date: date,
    settings: WorkSettings,
    tz: str,
    leave_intervals: tuple = (),
) -> datetime:
    """當日「應到班時間」：遲到判定與到班偏移量共用的基準。

    從表定上班時間起，反覆跳過「涵蓋游標」的已核准請假區間（只有從一早就連續
    涵蓋的請假會延後到班基準；中午才開始、或與上班時間不相鄰的假不影響這裡）；
    跳完後若落在表定午休區間內，再跳到午休結束——半天假下午回來上班，中間本來
    就有一段午休銜接，不該被算成遲到。

    無請假時回傳值恆等於表定上班時間。
    """
    day_start = at(punch_date, time(0, 0), tz)
    day_end = day_start + timedelta(days=1)

    cursor = at(punch_date, settings.work_start, tz)

    clamped = sorted((max(start, day_start), min(end, day_end)) for start, end in leave_intervals)

    changed = True
    while changed:
        changed = False
        for start, end in clamped:
            if start <= cursor < end:
                cursor = end
                changed = True

    lunch_start = at(punch_date, settings.lunch_start, tz)
    lunch_end = at(punch_date, settings.lunch_end, tz)
    if lunch_start <= cursor < lunch_end:
        cursor = lunch_end

    return cursor


def compute_arrival_offset(
    punch_in_time: datetime,
    punch_date: date,
    settings: WorkSettings,
    tz: str,
    expected_start: datetime | None = None,
) -> timedelta:
    """到班偏移量（雙向），值域固定為 `[−grace, +grace]`。

    晚到為正值，午休與正常工時結束同步往後；早到為負值，同步往前——否則
    「提早到班多做的時間」會被誤算進工時（08:48 上班、12:48 下班會變成 3.20 小時）。

    錨點預設為 `expected_start`；若打卡時間已達**表定**午休開始（不是浮動後的
    午休，避免循環依賴），錨點改為 `max(expected_start, 表定午休結束)`，且下限
    收斂為 0——上午整段已經錯過，那不叫「提早到班」，不該倒給緩衝。
    """
    punch_in_time = truncate_to_minute(punch_in_time)
    if expected_start is None:
        expected_start = at(punch_date, settings.work_start, tz)
    else:
        expected_start = truncate_to_minute(expected_start)

    lunch_start = at(punch_date, settings.lunch_start, tz)
    lunch_end = at(punch_date, settings.lunch_end, tz)

    anchor = expected_start
    lower_bound = -settings.grace
    if punch_in_time >= lunch_start:
        anchor = max(anchor, lunch_end)
        lower_bound = timedelta(0)

    offset = punch_in_time - anchor
    return max(lower_bound, min(offset, settings.grace))


def compute_work_start(
    punch_in_time: datetime,
    punch_date: date,
    settings: WorkSettings,
    tz: str,
    expected_start: datetime | None = None,
) -> datetime:
    """工時起算點 ＝ max(實際打卡時間, 應到班時間 + 到班偏移量)。

    偏移量非負時（準點或遲到）恆等於實際打卡時間；只有「早於緩衝窗到班」才會被
    墊高——提早超過緩衝的部分不計入工時，要認列請走加班申請。
    """
    punch_in_time = truncate_to_minute(punch_in_time)
    if expected_start is None:
        expected_start = at(punch_date, settings.work_start, tz)
    else:
        expected_start = truncate_to_minute(expected_start)

    offset = compute_arrival_offset(punch_in_time, punch_date, settings, tz, expected_start)
    return max(punch_in_time, expected_start + offset)


def floating_lunch_window(
    punch_in_time: datetime,
    punch_date: date,
    settings: WorkSettings,
    tz: str,
    expected_start: datetime | None = None,
) -> tuple[datetime, datetime]:
    """午休區間跟隨到班偏移量浮動（偏移量已封頂在緩衝值域，不會把午休推到深夜）。

    **這是出勤打卡專用的規則**：請假時數計算的午休固定不浮動（見 leave_hours.py），
    兩者刻意不同，不是不一致的 bug。
    """
    offset = compute_arrival_offset(punch_in_time, punch_date, settings, tz, expected_start)
    return (
        at(punch_date, settings.lunch_start, tz) + offset,
        at(punch_date, settings.lunch_end, tz) + offset,
    )


def daily_target(settings: WorkSettings, leave_hours: float = 0.0) -> timedelta:
    """當日應工作時數 ＝ 表定工時 − 表定午休長度 − 當日已核准請假時數。

    午休長度跟著設定連動，不硬編碼 1 小時：管理者把午休改成非 1 小時，這裡要同步。
    """
    target = settings.scheduled_duration - settings.lunch_duration - timedelta(hours=leave_hours)
    return target if target > timedelta(0) else timedelta(0)


def daily_work_hours(settings: WorkSettings) -> float:
    """一個完整工作日等於幾小時，供假別配額換算「天」為「小時」、以及判斷整天請假使用。"""
    return daily_target(settings).total_seconds() / 3600


def compute_normal_work_end(
    punch_in_time: datetime,
    punch_date: date,
    settings: WorkSettings,
    tz: str,
    expected_start: datetime | None = None,
    leave_hours: float = 0.0,
) -> datetime:
    """今天的「正常工時結束時間」＝ min(封頂式, 累積式)。

    1. **封頂式** ＝ 表定下班時間 + 到班偏移量。沒有它，極晚到班的人正常工時會
       一路算到半夜；輕微遲到（09:23 上班）也會被完整計滿 8 小時。
    2. **累積式** ＝ 從工時起算點累積滿當日應工時，跳過浮動午休。沒有它，
       「下午已請假 5 小時、09:02 上班、12:02 下班」會被誤判早退——那天做滿扣假後
       剩下的 3 小時就該下班了。

    取兩者較小：多數情境封頂式較小（限制遲到的影響範圍），下午請假的情境累積式較小。
    """
    punch_in_time = truncate_to_minute(punch_in_time)
    if expected_start is None:
        expected_start = at(punch_date, settings.work_start, tz)
    else:
        expected_start = truncate_to_minute(expected_start)

    offset = compute_arrival_offset(punch_in_time, punch_date, settings, tz, expected_start)
    capped_end = at(punch_date, settings.work_end, tz) + offset

    work_start = compute_work_start(punch_in_time, punch_date, settings, tz, expected_start)
    target = daily_target(settings, leave_hours)
    lunch_start, lunch_end = floating_lunch_window(punch_in_time, punch_date, settings, tz, expected_start)

    if lunch_end <= work_start:
        cumulative_end = work_start + target
    else:
        before_lunch = lunch_start - work_start
        if before_lunch >= target:
            cumulative_end = work_start + target
        else:
            cumulative_end = lunch_end + (target - before_lunch)

    return min(capped_end, cumulative_end)


def judge_status(
    punch_in_time: datetime,
    punch_date: date,
    settings: WorkSettings,
    tz: str,
    expected_start: datetime | None = None,
) -> str:
    """遲到判定，僅適用於工作日（非工作日一律 holiday_work，由呼叫端處理）。

    判定邊界為 `<=`：打卡時間等於截止時刻仍視為 normal。粒度是**分鐘**不是秒——
    09:10:00 與 09:10:59 都是 09 點 10 分，不該判成不同結果。
    """
    punch_in_time = truncate_to_minute(punch_in_time)
    if expected_start is None:
        expected_start = at(punch_date, settings.work_start, tz)
    deadline = truncate_to_minute(expected_start) + settings.grace
    return "normal" if punch_in_time <= deadline else "late"


def judge_early_leave(punch_out_time: datetime | None, normal_end: datetime | None, workday: bool) -> bool:
    """早退判定：`punch_out < normal_end` 即成立，**沒有任何寬限**。

    緩衝時間只用在到班那一端（遲到寬限、提早到班的工時起算），下班端不適用——
    一天該做滿的工時（已含請假與補打卡調整）就是要做滿到那一刻。這是刻意的不對稱。

    非工作日、尚未下班打卡、或無正常工時結束時間可比較時一律視為不早退。
    """
    if not workday or not punch_out_time or normal_end is None:
        return False
    return truncate_to_minute(punch_out_time) < truncate_to_minute(normal_end)


def _effective_work(
    from_time: datetime,
    to_time: datetime,
    punch_date: date,
    settings: WorkSettings,
    tz: str,
    expected_start: datetime | None = None,
) -> timedelta:
    """區間長度扣除與浮動午休的重疊。"""
    from_time = truncate_to_minute(from_time)
    to_time = truncate_to_minute(to_time)
    if to_time <= from_time:
        return timedelta(0)

    lunch_start, lunch_end = floating_lunch_window(from_time, punch_date, settings, tz, expected_start)
    duration = to_time - from_time
    overlap_start = max(from_time, lunch_start)
    overlap_end = min(to_time, lunch_end)
    if overlap_end > overlap_start:
        duration -= overlap_end - overlap_start
    return duration


def calculate_work_hours(
    punch_in_time: datetime | None,
    punch_out_time: datetime | None,
    punch_date: date,
    settings: WorkSettings,
    tz: str,
    workday: bool = True,
    expected_start: datetime | None = None,
    leave_hours: float = 0.0,
) -> float | None:
    """當日工時：只反映「正常工時」的部分，扣除浮動午休。

    工作日超過正常工時結束時間的部分不計入，要認列須另送加班申請。非工作日沒有
    「應到班時間」的概念，整段扣午休後的時間全額計入（全部視為待認列的加班），
    起點維持實際打卡時間——否則假日一早到班反而會被套用平日的緩衝上限而少算。
    """
    if not punch_in_time or not punch_out_time:
        return None

    punch_in_time = truncate_to_minute(punch_in_time)
    punch_out_time = truncate_to_minute(punch_out_time)

    capped_out_time = punch_out_time
    work_start = punch_in_time
    if workday:
        normal_end = compute_normal_work_end(
            punch_in_time, punch_date, settings, tz, expected_start, leave_hours
        )
        if capped_out_time > normal_end:
            capped_out_time = normal_end
        work_start = compute_work_start(punch_in_time, punch_date, settings, tz, expected_start)

    duration = _effective_work(work_start, capped_out_time, punch_date, settings, tz, expected_start)
    return round(duration.total_seconds() / 3600 * 100) / 100


def compute_overtime_eligible_start(
    punch_in_time: datetime,
    punch_date: date,
    settings: WorkSettings,
    tz: str,
    workday: bool = True,
    expected_start: datetime | None = None,
    leave_hours: float = 0.0,
) -> datetime:
    """加班最早可認列的起點：工作日為正常工時結束後休息 30 分鐘；非工作日沒有
    「正常工時」，整段在班時間都待認列，故直接以上班打卡時間為起點。

    非工作日分支同樣先截斷到分鐘——帶著秒數會比 API 傳入、已截斷的申請起始時間
    還晚，造成「08:56 打卡卻被告知最早只能從 08:56 開始申請」這種自相矛盾的防呆。
    """
    if not workday:
        return truncate_to_minute(punch_in_time)
    normal_end = compute_normal_work_end(
        punch_in_time, punch_date, settings, tz, expected_start, leave_hours
    )
    return normal_end + OVERTIME_REST
