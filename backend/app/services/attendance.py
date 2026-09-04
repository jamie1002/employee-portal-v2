"""打卡與出勤查詢的業務邏輯。

所有時間戳一律取自虛擬時鐘（`get_virtual_now()`），營業日一律走
`get_business_date()`——用 UTC 日期會把台灣早班打卡記到前一天，並沿著
`UNIQUE(user_id, punch_date)` 污染後續的補打卡目標列（見 docs/PITFALLS.md B1）。
"""

import asyncio
from datetime import date

import asyncpg

from app.config.settings import app_settings
from app.repositories import attendance_repository, leave_request_repository, settings_repository
from app.repositories import user_repository
from app.services import attendance_effective
from app.services.leave_hours import compute_leave_hours_for_date
from app.services.work_hours import (
    LATE_PUNCH_OUT_MARGIN,
    WorkSettings,
    calculate_work_hours,
    compute_expected_start,
    compute_normal_work_end,
    compute_overtime_eligible_start,
    judge_early_leave,
    judge_status,
)
from app.services.workday import is_workday
from app.utils.errors import AppError
from app.utils.timezone import get_business_date
from app.utils.virtual_clock import get_virtual_now

NOTE_PERSONAL_BUSINESS = "處理私人事務"

# 未指定查詢區間時的邊界，涵蓋所有可能的業務日期。
EARLIEST_QUERY_DATE = date(2000, 1, 1)
LATEST_QUERY_DATE = date(2100, 12, 31)


def _with_punch_flags(record: asyncpg.Record) -> dict:
    row = dict(record)
    return {
        **row,
        "has_punched_in": bool(row["punch_in_time"]),
        "has_punched_out": bool(row["punch_out_time"]),
    }


async def _leave_context(
    pool: asyncpg.Pool, user_id: int, punch_date: date, settings: WorkSettings, tz: str, workday: bool
):
    """打卡當下查出當日已核准請假，算出應到班時間與當日已請假時數。
    非工作日沒有這些概念，直接回傳無請假的預設值。"""
    if not workday:
        return None, 0.0
    intervals = await leave_request_repository.find_approved_intervals_for_date(pool, user_id, punch_date, tz)
    expected_start = compute_expected_start(punch_date, settings, tz, intervals)
    leave_hours = compute_leave_hours_for_date(punch_date, intervals, settings, tz)
    return expected_start, leave_hours


async def punch_in(pool: asyncpg.Pool, user_id: int) -> dict:
    tz = app_settings.APP_TIMEZONE
    now = await get_virtual_now()
    punch_date = get_business_date(now, tz=tz)

    existing = await attendance_repository.find_by_user_and_date(pool, user_id, punch_date)
    if existing and existing["punch_in_time"]:
        raise AppError(409, "今日已完成上班打卡。", "ALREADY_PUNCHED_IN")

    settings_row, workday = await asyncio.gather(
        settings_repository.get_settings(pool),
        is_workday(pool, punch_date),
    )
    settings = WorkSettings.from_row(settings_row)
    expected_start, leave_hours = await _leave_context(pool, user_id, punch_date, settings, tz, workday)

    # 非工作日不做遲到判定：整段在班時間都是待認列的假日出勤。
    status = judge_status(now, punch_date, settings, tz, expected_start) if workday else "holiday_work"

    punch_out_time = existing["punch_out_time"] if existing else None
    work_hours = calculate_work_hours(
        now, punch_out_time, punch_date, settings, tz, workday,
        expected_start=expected_start, leave_hours=leave_hours,
    )
    is_early_leave = False
    if punch_out_time:
        normal_end = compute_normal_work_end(now, punch_date, settings, tz, expected_start, leave_hours)
        is_early_leave = judge_early_leave(punch_out_time, normal_end, workday)

    record = await attendance_repository.upsert_attendance(
        pool, user_id, punch_date, now, punch_out_time, status, work_hours, now,
        is_early_leave=is_early_leave,
    )
    return {**_with_punch_flags(record), "is_workday": workday}


async def punch_out(pool: asyncpg.Pool, user_id: int) -> dict:
    tz = app_settings.APP_TIMEZONE
    now = await get_virtual_now()
    punch_date = get_business_date(now, tz=tz)

    existing = await attendance_repository.find_by_user_and_date(pool, user_id, punch_date)
    if not existing or not existing["punch_in_time"]:
        raise AppError(400, "尚未完成上班打卡，無法進行下班打卡。", "NOT_PUNCHED_IN")
    if existing["punch_out_time"]:
        raise AppError(409, "今日已完成下班打卡。", "ALREADY_PUNCHED_OUT")

    settings_row, workday = await asyncio.gather(
        settings_repository.get_settings(pool),
        is_workday(pool, punch_date),
    )
    settings = WorkSettings.from_row(settings_row)
    expected_start, leave_hours = await _leave_context(pool, user_id, punch_date, settings, tz, workday)

    punch_in_time = existing["punch_in_time"]
    work_hours = calculate_work_hours(
        punch_in_time, now, punch_date, settings, tz, workday,
        expected_start=expected_start, leave_hours=leave_hours,
    )
    normal_end = compute_normal_work_end(punch_in_time, punch_date, settings, tz, expected_start, leave_hours)
    overtime_eligible_start = compute_overtime_eligible_start(
        punch_in_time, punch_date, settings, tz, workday,
        expected_start=expected_start, leave_hours=leave_hours,
    )
    is_early_leave = judge_early_leave(now, normal_end, workday)

    record = await attendance_repository.upsert_attendance(
        pool, user_id, punch_date, punch_in_time, now, existing["status"], work_hours, now,
        is_early_leave=is_early_leave,
    )
    return {
        **_with_punch_flags(record),
        "is_workday": workday,
        "normal_work_end": normal_end,
        "overtime_eligible_start": overtime_eligible_start,
        # 晚下班提示的門檻由後端算出，前端不得自行推算——寫死的「19 點」與正常工時
        # 結束時間無關，08:50 上班的人 18:50 已加班 30 分鐘卻不會提示（見 SPEC.md §4.1.6）。
        "late_punch_out_threshold": normal_end + LATE_PUNCH_OUT_MARGIN,
    }


async def mark_today_note(pool: asyncpg.Pool, user_id: int) -> dict:
    """下班打卡後若選擇「算作處理私人事務」，把固定文字寫入當日出勤備註。

    只接受伺服器端寫死的文字、不接受前端傳入內容——目前不開放員工自行填寫，
    因此也不需要額外的輸入清洗。
    """
    tz = app_settings.APP_TIMEZONE
    now = await get_virtual_now()
    punch_date = get_business_date(now, tz=tz)

    record = await attendance_repository.set_note(pool, user_id, punch_date, NOTE_PERSONAL_BUSINESS, now)
    if record is None:
        raise AppError(400, "今日尚無出勤紀錄，無法標註備註。", "NO_ATTENDANCE_TODAY")
    return dict(record)


async def get_today(pool: asyncpg.Pool, user_id: int) -> dict:
    tz = app_settings.APP_TIMEZONE
    now = await get_virtual_now()
    punch_date = get_business_date(now, tz=tz)

    # 兩者互不依賴，依序 await 只是白白多等一趟資料庫往返。
    resolved, workday = await asyncio.gather(
        attendance_effective.resolve_one(pool, user_id, punch_date),
        is_workday(pool, punch_date),
    )

    if not resolved:
        return {
            "punch_date": punch_date,
            "punch_in_time": None,
            "punch_out_time": None,
            "status": None,
            "work_hours": None,
            "has_punched_in": False,
            "has_punched_out": False,
            "is_workday": workday,
        }
    return {**resolved, "is_workday": workday}


def matches_status_filter(record: dict, status: str | None) -> bool:
    """狀態篩選一律比對**生效值**。

    `early_leave`／`missing_punch_out` 是衍生判定，不是 status 欄位的列舉值，
    要另外比對對應的布林欄位。篩「正常」時**必須同時排除**早退與未打下班卡的日子
    ——那些日子的 effective_status 仍是 normal（遲到與否跟有沒有打下班卡是兩件事），
    但畫面上會同時顯示「早退」徽章，篩選結果卻宣稱它正常，兩者矛盾。
    """
    if status is None:
        return True
    if status == "early_leave":
        return bool(record["effective_is_early_leave"])
    if status == "missing_punch_out":
        return bool(record["is_missing_punch_out"])
    if status == "normal":
        return (
            record["effective_status"] == "normal"
            and not record["effective_is_early_leave"]
            and not record["is_missing_punch_out"]
        )
    return record["effective_status"] == status


async def get_my_records(
    pool: asyncpg.Pool,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """生效值於讀取時算出，分頁隨之從 SQL 移到應用層——量體是「每人每月約 22 個
    工作日」，全量撈回後切頁沒有效能疑慮。"""
    all_records = await attendance_effective.resolve_range(
        pool, [user_id], start_date or EARLIEST_QUERY_DATE, end_date or LATEST_QUERY_DATE
    )
    filtered = [row for row in all_records if matches_status_filter(row, status)]
    start = (page - 1) * page_size
    return {
        "records": filtered[start : start + page_size],
        "total": len(filtered),
        "page": page,
        "page_size": page_size,
    }


async def get_all(
    pool: asyncpg.Pool,
    user_id: int | None = None,
    department_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
) -> list[dict]:
    if user_id:
        user_ids = [user_id]
    else:
        members = await user_repository.find_all(pool, department_id=department_id)
        user_ids = [member["id"] for member in members]

    all_records = await attendance_effective.resolve_range(
        pool, user_ids, start_date or EARLIEST_QUERY_DATE, end_date or LATEST_QUERY_DATE
    )
    return [row for row in all_records if matches_status_filter(row, status)]
