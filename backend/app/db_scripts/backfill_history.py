"""展示資料的歷史出勤回填（2026-05-01 ~ 2026-08-23，虛擬時鐘展示視窗 08/24 的前一天）。

由 `seed_business_data.py` 在寫完劇本式的近兩週示範資料後呼叫（見該檔案），確保
每次展示資料重置／初始種子都會有半年份的歷史出勤可供「出勤紀錄」「全公司出勤」
分頁展示分頁與篩選，不是只有近兩週幾筆資料。

比例固定：正常 85%、遲到 8%、曠職 2%、已核准整天請假 5%——用固定種子的
`random.Random(42)`（不是模組層級共用的 random），確保每次重置展示資料都產出
完全相同的歷史紀錄，展示效果才穩定可預期。

工時／狀態／請假時數一律呼叫正式的業務純函式算出，不手刻 literal，確保回填資料
永遠跟正式規則同步（見 docs/PITFALLS.md E1）。

用 `INSERT ... ON CONFLICT (user_id, punch_date) DO NOTHING` 一次性批次寫入：
- 效能上，全公司歷史工作日數量頗大（5 個月 × 多位使用者），逐列 await 資料庫
  來回會拖慢整個展示資料重置流程。
- 語意上，`seed_business_data()` 已經為特定使用者手動寫好近兩週的劇本式出勤／
  請假（例如陳小華 08/19 的整天特別休假），回填必須「補洞」而非覆蓋——
  DO NOTHING 讓已存在的劇本資料原封不動，只填其餘沒被劇本點名的工作日。
  因此呼叫順序上，本函式必須排在 seed_business_data() 的劇本式資料之後。

已知的可接受邊界情況：隨機回填的「整天請假」若剛好落在某使用者已被劇本手動
指定請假的同一天以外的日期，彼此互不影響；若剛好與劇本指定的請假同一天，
attendances 表的 UNIQUE(user_id, punch_date) 加上 DO NOTHING 保證出勤紀錄不衝突，
但 leave_requests 沒有相同的唯一鍵，理論上可能生出同一天兩筆請假紀錄。發生機率
極低（各 5% 機率的隨機事件剛好命中同一天）且純屬展示資料的美觀瑕疵、不影響任何
業務規則正確性，故不特別處理（沿用前一版同樣的取捨）。
"""

import random
from datetime import date, time, timedelta

import asyncpg

from app.services.leave_hours import calculate_leave_hours_by_day
from app.services.work_hours import WorkSettings, at, calculate_work_hours, judge_status
from app.utils.pg_types import pg_date

BACKFILL_START = date(2026, 5, 1)
BACKFILL_END = date(2026, 8, 23)
RANDOM_SEED = 42
TZ = "Asia/Taipei"

# 累積機率門檻：normal 85%、late 8%、absent 2%，其餘 5% 為已核准整天請假。
_NORMAL_THRESHOLD = 0.85
_LATE_THRESHOLD = 0.93
_ABSENT_THRESHOLD = 0.95

LEAVE_TYPES = ["特別休假", "事假", "病假"]
LEAVE_REASONS = {"特別休假": "安排個人行程", "事假": "個人事務", "病假": "身體不適就醫"}


def _iter_workdays(start: date, end: date, holiday_dates: set[date]):
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holiday_dates:  # Monday=0 ... Sunday=6
            yield current
        current += timedelta(days=1)


def _build_punch_day(
    user_id: int, day: date, settings: WorkSettings, in_offset_minutes: int, out_offset_minutes: int
) -> tuple:
    punch_in_time = at(day, settings.work_start, TZ) + timedelta(minutes=in_offset_minutes)
    punch_out_time = at(day, settings.work_end, TZ) + timedelta(minutes=out_offset_minutes)

    status = judge_status(punch_in_time, day, settings, TZ)
    work_hours = calculate_work_hours(punch_in_time, punch_out_time, day, settings, TZ, workday=True)
    return (user_id, pg_date(day), punch_in_time, punch_out_time, status, work_hours)


def _build_full_day_leave(
    user_id: int, day: date, leave_type: str, settings: WorkSettings, reviewer_id: int
) -> tuple | None:
    start_time = at(day, settings.work_start, TZ)
    end_time = at(day, settings.work_end, TZ)

    by_day = calculate_leave_hours_by_day(start_time, end_time, settings, TZ, holiday_dates=set())
    hours = round(by_day.get(day, 0.0) * 100) / 100
    if hours <= 0:
        return None
    return (user_id, pg_date(day), start_time, end_time, hours, leave_type, reviewer_id)


def _reviewer_for(user: asyncpg.Record, department_managers: dict[int, int]) -> int:
    """已核准的請假不可沒有審核者。優先取該員工所屬部門的主管；查不到（無部門、
    或該員工本身就是部門主管，不能自審）時退回 admin（id=1）——admin 對自己送出
    的申請本就有自審豁免。
    """
    manager_id = department_managers.get(user["department_id"])
    if manager_id and manager_id != user["id"]:
        return manager_id
    return 1


async def run_backfill(conn: asyncpg.Connection, settings: WorkSettings) -> None:
    holiday_dates = {r["holiday_date"] for r in await conn.fetch("SELECT holiday_date FROM holidays")}
    users = await conn.fetch("SELECT id, hire_date, department_id FROM users ORDER BY id")
    department_managers = {
        r["id"]: r["manager_id"] for r in await conn.fetch("SELECT id, manager_id FROM departments")
    }

    rng = random.Random(RANDOM_SEED)
    grace_minutes = settings.grace_minutes

    attendance_rows: list[tuple] = []
    leave_rows: list[tuple] = []

    for user in users:
        start = max(BACKFILL_START, user["hire_date"])
        if start > BACKFILL_END:
            continue  # 到職日晚於整個回填視窗（剛到職的新人），沒有歷史可回填。

        reviewer_id = _reviewer_for(user, department_managers)

        for day in _iter_workdays(start, BACKFILL_END, holiday_dates):
            roll = rng.random()

            if roll < _NORMAL_THRESHOLD:
                in_offset = rng.randint(0, grace_minutes)
                out_offset = rng.randint(0, 20)
                attendance_rows.append(_build_punch_day(user["id"], day, settings, in_offset, out_offset))
            elif roll < _LATE_THRESHOLD:
                in_offset = rng.randint(grace_minutes + 1, grace_minutes + 35)
                out_offset = rng.randint(0, 20)
                attendance_rows.append(_build_punch_day(user["id"], day, settings, in_offset, out_offset))
            elif roll < _ABSENT_THRESHOLD:
                attendance_rows.append((user["id"], pg_date(day), None, None, "absent", None))
            else:
                leave_type = rng.choice(LEAVE_TYPES)
                built = _build_full_day_leave(user["id"], day, leave_type, settings, reviewer_id)
                if built:
                    leave_rows.append(built)

    if attendance_rows:
        await conn.execute(
            """INSERT INTO attendances (
                 user_id, punch_date, punch_in_time, punch_out_time, status, work_hours
               )
               SELECT * FROM unnest(
                 $1::int[], $2::date[], $3::timestamptz[], $4::timestamptz[], $5::varchar[], $6::numeric[]
               )
               ON CONFLICT (user_id, punch_date) DO NOTHING""",
            [r[0] for r in attendance_rows],
            [r[1] for r in attendance_rows],
            [r[2] for r in attendance_rows],
            [r[3] for r in attendance_rows],
            [r[4] for r in attendance_rows],
            [r[5] for r in attendance_rows],
        )

    if leave_rows:
        # reason 依 leave_type 對應查表帶入，型別跟其餘欄位不同，故不併進同一組
        # unnest 陣列；reviewer_id 必填（已核准不可無審核者）。created_at／reviewed_at
        # 刻意不等於同一時間點（那等於零前置時間送出又立刻核准，時序不合理）——
        # 改為 created_at＝請假開始時間前 3 天、reviewed_at＝前 2 天，維持
        # 「送出 → 核准 → 開始」的合理先後順序。
        reasons = [LEAVE_REASONS[row[5]] for row in leave_rows]
        await conn.execute(
            """INSERT INTO leave_requests (
                 user_id, leave_type, start_time, end_time, hours, reason, status,
                 created_at, reviewer_id, reviewed_at
               )
               SELECT u, lt, st, et, h, rs, 'approved', st - INTERVAL '3 days', rv, st - INTERVAL '2 days'
               FROM unnest(
                 $1::int[], $2::varchar[], $3::timestamptz[], $4::timestamptz[], $5::numeric[], $6::text[], $7::int[]
               ) AS t(u, lt, st, et, h, rs, rv)""",
            [row[0] for row in leave_rows],
            [row[5] for row in leave_rows],
            [row[2] for row in leave_rows],
            [row[3] for row in leave_rows],
            [row[4] for row in leave_rows],
            reasons,
            [row[6] for row in leave_rows],
        )
