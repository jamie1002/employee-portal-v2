"""假別配額計算（SPEC.md §4.3.1）。純函式即時算出，不落地儲存。

事假／病假／公假採**曆年制**（每年 1/1 歸零）；特別休假採**到職週年制**
（勞基法第 38 條），配額隨到職年資逐年遞增。
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import asyncpg

from app.config.settings import app_settings
from app.repositories import leave_request_repository, settings_repository
from app.services.work_hours import WorkSettings, daily_work_hours

# 假別鍵 → 曆年制年度天數（None 代表不設固定上限，只登記已使用時數）。
CALENDAR_YEAR_TYPES: dict[str, int | None] = {
    "事假": 14,
    "病假": 30,
    "公假": None,
}


def special_leave_days(total_months: int) -> int:
    """純函式：勞基法第 38 條特別休假天數對照表。
    `total_months` 為該期間起點時已滿的完整到職月數（例：滿 3 年整＝36）。
    """
    if total_months < 6:
        return 0
    if total_months < 12:
        return 3
    years = total_months // 12
    if years == 1:
        return 7
    if years == 2:
        return 10
    if 3 <= years < 5:
        return 14
    if 5 <= years < 10:
        return 15
    # 勞基法第 38 條「十年以上者，每一年加給一日，加至三十日為止」：
    # 滿 10 年即為 16 日（不是與滿 5 年同為 15 日），故基準是 years - 9 而非 years - 10；
    # 依此滿 24 年剛好觸及 30 日上限。
    return min(15 + (years - 9), 30)


def _add_months_clamped(d: date, months: int) -> date:
    """把日期往後加 n 個月，日期超過該月天數上限時自動夾在月底
    （例：1/31 加一個月 → 2/28，不是溢位成 3/3）。"""
    total_month_index = (d.month - 1) + months
    new_year = d.year + total_month_index // 12
    new_month = total_month_index % 12 + 1
    next_month_first = date(new_year + (1 if new_month == 12 else 0), 1 if new_month == 12 else new_month + 1, 1)
    this_month_first = date(new_year, new_month, 1)
    days_in_new_month = (next_month_first - this_month_first).days
    return date(new_year, new_month, min(d.day, days_in_new_month))


def _months_since(hire_date: date, today: date) -> int:
    months = (today.year - hire_date.year) * 12 + (today.month - hire_date.month)
    if today.day < hire_date.day:
        months -= 1
    return max(months, 0)


@dataclass(frozen=True)
class SpecialLeavePeriod:
    period_start: date
    period_end: date
    days: int


def current_special_leave_period(hire_date: date, today: date) -> SpecialLeavePeriod:
    """算出「今天」所屬的特別休假到職週年制區間：`[period_start, period_end)` 與該區間的配額天數。"""
    months = _months_since(hire_date, today)

    if months < 6:
        return SpecialLeavePeriod(hire_date, _add_months_clamped(hire_date, 6), 0)
    if months < 12:
        return SpecialLeavePeriod(_add_months_clamped(hire_date, 6), _add_months_clamped(hire_date, 12), 3)

    k = months // 12
    return SpecialLeavePeriod(
        _add_months_clamped(hire_date, 12 * k),
        _add_months_clamped(hire_date, 12 * (k + 1)),
        special_leave_days(12 * k),
    )


def _to_utc_midnight(d: date, tz: str) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)


async def get_my_leave_quota(pool: asyncpg.Pool, user: dict, today: date) -> list[dict]:
    """回傳四種假別在「目前所屬計算週期」的配額／已用／剩餘時數。"""
    tz = app_settings.APP_TIMEZONE
    settings = WorkSettings.from_row(await settings_repository.get_settings(pool))
    hours_per_day = daily_work_hours(settings)

    calendar_year_start = date(today.year, 1, 1)
    calendar_year_end = date(today.year + 1, 1, 1)

    results = []

    special_period = current_special_leave_period(user["hire_date"], today)
    special_quota_hours = round(special_period.days * hours_per_day * 100) / 100
    special_used_hours = await leave_request_repository.sum_approved_hours_in_period(
        pool,
        user["id"],
        "特別休假",
        _to_utc_midnight(special_period.period_start, tz),
        _to_utc_midnight(special_period.period_end, tz),
    )
    results.append({
        "leave_type": "特別休假",
        "quota_hours": special_quota_hours,
        "used_hours": special_used_hours,
        "remaining_hours": round((special_quota_hours - special_used_hours) * 100) / 100,
        "period_start": special_period.period_start,
        "period_end": special_period.period_end,
    })

    for leave_type, annual_days in CALENDAR_YEAR_TYPES.items():
        used_hours = await leave_request_repository.sum_approved_hours_in_period(
            pool,
            user["id"],
            leave_type,
            _to_utc_midnight(calendar_year_start, tz),
            _to_utc_midnight(calendar_year_end, tz),
        )
        quota_hours = None if annual_days is None else round(annual_days * hours_per_day * 100) / 100
        results.append({
            "leave_type": leave_type,
            "quota_hours": quota_hours,
            "used_hours": used_hours,
            "remaining_hours": None if quota_hours is None else round((quota_hours - used_hours) * 100) / 100,
            "period_start": calendar_year_start,
            "period_end": calendar_year_end,
        })

    return results
