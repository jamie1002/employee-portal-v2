"""出勤生效值解析（SPEC.md §4.2：出勤資料純衍生）。

`attendances` 只保存原始打卡事實；補打卡與請假核准**不覆寫**這張表，異動後的
「生效值」在讀取時 join 已核准申請單即時算出，不落地。

**所有出勤讀取路徑（個人紀錄、全公司紀錄、今日狀態、匯出）都必須經過這裡**，
不得各自重算一套——那正是兩份規則開始分岔的起點。
"""

import asyncio
from collections import defaultdict
from datetime import date, timedelta

import asyncpg

from app.config.settings import app_settings
from app.repositories import (
    attendance_repository,
    holiday_repository,
    leave_request_repository,
    punch_request_repository,
    settings_repository,
    user_repository,
)
from app.services.leave_hours import calculate_leave_hours_by_day, compute_leave_hours_for_date
from app.services.work_hours import (
    WorkSettings,
    calculate_work_hours,
    compute_expected_start,
    compute_normal_work_end,
    daily_work_hours,
    format_hours,
    judge_early_leave,
    judge_status,
)
from app.services.workday import is_weekend
from app.utils.timezone import get_business_date
from app.utils.virtual_clock import get_virtual_now


def _dates_between(start_date: date, end_date: date) -> list[date]:
    days = []
    cursor = start_date
    while cursor <= end_date:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def resolve_row(
    *,
    punch_date: date,
    raw_row: asyncpg.Record | None,
    approved_punch_request: asyncpg.Record | None,
    leave_intervals,
    full_day_leave_hours: float | None,
    settings: WorkSettings,
    tz: str,
    workday: bool,
    today: date,
    user: asyncpg.Record | None = None,
    has_changes: bool = False,
) -> dict:
    """純函式：把「一天的原始出勤列（可能不存在）＋ 當天已核准的補打卡／請假」
    解析成生效值。呼叫端負責先備妥 workday／today／leave_intervals 等上下文。

    `is_adjusted` 與 `has_changes` 語意不同、不可合併：前者只在已核准且真的改動了
    生效值時才為真；後者純粹標記「這天有異動申請」，即使還在待審或已被駁回也一樣
    ——否則被駁回或待審的日子在畫面上完全看不出動過。
    """
    requested_in = approved_punch_request["requested_in_time"] if approved_punch_request else None
    requested_out = approved_punch_request["requested_out_time"] if approved_punch_request else None

    effective_in = requested_in or (raw_row["punch_in_time"] if raw_row else None)
    effective_out = requested_out or (raw_row["punch_out_time"] if raw_row else None)

    is_full_day_leave = full_day_leave_hours is not None
    is_adjusted = bool(requested_in or requested_out) or is_full_day_leave

    if not workday:
        effective_status = "holiday_work" if effective_in else (raw_row["status"] if raw_row else None)
        effective_work_hours = None
        effective_is_early_leave = False
    elif is_full_day_leave:
        effective_status = "on_leave"
        effective_work_hours = round(full_day_leave_hours * 100) / 100
        effective_is_early_leave = False
    elif effective_in:
        expected_start = compute_expected_start(punch_date, settings, tz, leave_intervals)
        leave_hours = compute_leave_hours_for_date(punch_date, leave_intervals, settings, tz)
        effective_status = judge_status(effective_in, punch_date, settings, tz, expected_start)
        effective_work_hours = calculate_work_hours(
            effective_in, effective_out, punch_date, settings, tz, workday,
            expected_start=expected_start, leave_hours=leave_hours,
        )
        effective_is_early_leave = False
        if effective_out:
            normal_end = compute_normal_work_end(
                effective_in, punch_date, settings, tz, expected_start, leave_hours
            )
            effective_is_early_leave = judge_early_leave(effective_out, normal_end, workday)
    else:
        effective_status = "absent"
        effective_work_hours = None
        effective_is_early_leave = False

    is_missing_punch_out = bool(workday and effective_in and not effective_out and punch_date < today)

    base = (
        dict(raw_row)
        if raw_row
        else {
            "id": None,
            "punch_in_time": None,
            "punch_out_time": None,
            "status": None,
            "work_hours": None,
            "is_early_leave": False,
            "note": None,
        }
    )

    result = {
        **base,
        "punch_date": punch_date,
        "effective_punch_in_time": effective_in,
        "effective_punch_out_time": effective_out,
        "effective_status": effective_status,
        "effective_work_hours": format_hours(effective_work_hours),
        "effective_is_early_leave": effective_is_early_leave,
        "is_missing_punch_out": is_missing_punch_out,
        "is_adjusted": is_adjusted,
        "has_changes": has_changes,
        "has_punched_in": bool(effective_in),
        "has_punched_out": bool(effective_out),
    }
    if user is not None:
        result["user_id"] = user["id"]
        result["employee_no"] = user["employee_no"]
        result["user_name"] = user["name"]
        result["department_id"] = user["department_id"]
        result["department_name"] = user["department_name"]
    return result


async def resolve_range(
    pool: asyncpg.Pool, user_ids: list[int], start_date: date, end_date: date
) -> list[dict]:
    """批次解析多位使用者在區間內的生效出勤列。涵蓋三種來源：

    ① 有原始出勤列的日子（實際打卡，或曠職排程補寫的 absent 列）；
    ② 有已核准整天請假的日子（即使當天完全沒有出勤列）；
    ③ 有已核准補打卡的日子（同樣可能沒有既有出勤列——整天忘記打卡）。

    三者皆無的日期不會出現在結果中（不做全月曆合成）。
    """
    if not user_ids:
        return []

    tz = app_settings.APP_TIMEZONE

    # 以下 9 個查詢彼此互不依賴（都只需要一開始就有的 user_ids／日期區間），依序
    # await 會把資料庫往返疊加成 9 倍延遲——在後端與資料庫跨區的部署環境下這是
    # 「喚醒後仍然很慢」的主因（見 docs/PITFALLS.md F1）。併發送出，總耗時趨近
    # 最慢的那一個。回傳資料與後續判定完全不變，純屬效能調整。
    (
        settings_row,
        virtual_now,
        raw_rows,
        users,
        approved_punches,
        approved_leaves,
        holiday_dates_list,
        all_punch_targets,
        all_leave_intervals,
    ) = await asyncio.gather(
        settings_repository.get_settings(pool),
        get_virtual_now(),
        attendance_repository.find_by_users_in_range(pool, user_ids, start_date, end_date),
        user_repository.find_by_ids(pool, user_ids),
        punch_request_repository.find_approved_in_range(pool, user_ids, start_date, end_date),
        leave_request_repository.find_approved_intervals_in_range(pool, user_ids, start_date, end_date, tz),
        holiday_repository.find_dates_in_range(pool, start_date, end_date),
        punch_request_repository.find_target_dates_in_range(pool, user_ids, start_date, end_date),
        leave_request_repository.find_any_status_intervals_in_range(pool, user_ids, start_date, end_date, tz),
    )

    settings = WorkSettings.from_row(settings_row)
    today = get_business_date(virtual_now, tz=tz)
    full_day_threshold = daily_work_hours(settings)
    holiday_dates = set(holiday_dates_list)

    users_by_id = {user["id"]: user for user in users}
    raw_by_key = {(row["user_id"], row["punch_date"]): row for row in raw_rows}
    punch_by_key = {(row["user_id"], row["target_date"]): row for row in approved_punches}

    intervals_by_user: dict[int, list[tuple]] = defaultdict(list)
    for row in approved_leaves:
        intervals_by_user[row["user_id"]].append((row["start_time"], row["end_time"]))

    leave_hours_by_key: dict[tuple[int, date], float] = defaultdict(float)
    for row in approved_leaves:
        by_day = calculate_leave_hours_by_day(
            row["start_time"], row["end_time"], settings, tz, holiday_dates=holiday_dates
        )
        for day, hours in by_day.items():
            if start_date <= day <= end_date:
                leave_hours_by_key[(row["user_id"], day)] += hours

    # 不分狀態的異動日期（對照上面兩個 by_key 只收已核准），供 has_changes 使用。
    change_dates_by_user: dict[int, set[date]] = defaultdict(set)
    for row in all_punch_targets:
        change_dates_by_user[row["user_id"]].add(row["target_date"])
    for row in all_leave_intervals:
        leave_start = max(get_business_date(row["start_time"], tz=tz), start_date)
        leave_end = min(get_business_date(row["end_time"], tz=tz), end_date)
        if leave_start <= leave_end:
            change_dates_by_user[row["user_id"]].update(_dates_between(leave_start, leave_end))

    keys = set(raw_by_key) | set(punch_by_key)
    for key, hours in leave_hours_by_key.items():
        if hours + 1e-9 >= full_day_threshold:
            keys.add(key)

    results = []
    for user_id, punch_date in keys:
        user = users_by_id.get(user_id)
        if user is None:
            continue
        day_leave_hours = leave_hours_by_key.get((user_id, punch_date))
        is_full_day = day_leave_hours is not None and day_leave_hours + 1e-9 >= full_day_threshold
        results.append(
            resolve_row(
                punch_date=punch_date,
                raw_row=raw_by_key.get((user_id, punch_date)),
                approved_punch_request=punch_by_key.get((user_id, punch_date)),
                leave_intervals=intervals_by_user.get(user_id, ()),
                full_day_leave_hours=day_leave_hours if is_full_day else None,
                settings=settings,
                tz=tz,
                workday=not is_weekend(punch_date) and punch_date not in holiday_dates,
                today=today,
                user=user,
                has_changes=punch_date in change_dates_by_user.get(user_id, ()),
            )
        )

    results.sort(key=lambda row: (row["punch_date"], row.get("user_name") or ""), reverse=True)
    return results


async def resolve_one(pool: asyncpg.Pool, user_id: int, punch_date: date) -> dict | None:
    """單一使用者、單一日期的生效出勤。完全沒有任何紀錄或申請時回傳 None。"""
    rows = await resolve_range(pool, [user_id], punch_date, punch_date)
    return rows[0] if rows else None


