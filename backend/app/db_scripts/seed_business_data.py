"""展示用業務資料（出勤／請假／加班／補打卡／場地預約）。

刻意不寫死任何**衍生值**（工時、狀態、加班可認列起點）——這裡只手動挑選看起來
合理的原始輸入（打卡時間、請假區間），衍生值一律呼叫正式的業務純函式算出再
代入。前一版曾經兩次讓種子資料自己過不了系統剛加上的防呆（示範加班申請的起始
時間早於系統算出的最早可申請時間），根因是沒有測試在驗證種子資料是否符合
業務規則——見 docs/PITFALLS.md E1，`tests/test_seed_business_rules.py` 就是
補這個洞的全表掃描測試。

所有日期一律是相對於虛擬時鐘重置起點 `DATE '2026-08-24'`（週一）的具體日期
字面值，不使用 `date.today()`（見 docs/PITFALLS.md E2）。

審核（核准／駁回）刻意繞過 `services/request_review.py`：那支服務一律用
`get_virtual_now()` 當作 `reviewed_at`，種子資料需要指定歷史上的審核時間，
必須直接呼叫 repository 的 `update_review()`（見 docs/PITFALLS.md E3：
`created_at` 必須早於 `reviewed_at`，順序不能顛倒）。
"""

from datetime import date, time, timedelta

import asyncpg

from app.config.settings import app_settings
from app.repositories import (
    attendance_repository,
    leave_request_repository,
    overtime_request_repository,
    punch_request_repository,
    room_booking_repository,
    settings_repository,
)
from app.services.leave_hours import calculate_leave_hours, calculate_overtime_hours
from app.services.work_hours import (
    WorkSettings,
    at,
    calculate_work_hours,
    compute_expected_start,
    compute_overtime_eligible_start,
    judge_status,
)

_TZ = app_settings.APP_TIMEZONE

ADMIN_ID = 1
MANAGER_ID = 2
EMPLOYEE_ID = 3
OTHER_MANAGER_ID = 4
OTHER_EMPLOYEE_ID = 5


def _hhmm(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":"))
    return time(hour, minute)


def _at(day: date, hhmm: str):
    return at(day, _hhmm(hhmm), _TZ)


async def _seed_attendance(conn: asyncpg.Connection, settings: WorkSettings, now, user_id: int, day: date, in_hhmm: str | None, out_hhmm: str | None) -> None:
    if in_hhmm is None:
        await attendance_repository.upsert_attendance(conn, user_id, day, None, None, "absent", None, now)
        return

    punch_in = _at(day, in_hhmm)
    punch_out = _at(day, out_hhmm) if out_hhmm else None
    expected_start = compute_expected_start(day, settings, _TZ)
    status = judge_status(punch_in, day, settings, _TZ, expected_start)
    work_hours = calculate_work_hours(punch_in, punch_out, day, settings, _TZ, workday=True, expected_start=expected_start)
    await attendance_repository.upsert_attendance(conn, user_id, day, punch_in, punch_out, status, work_hours, now)


async def _seed_leave_request(
    conn: asyncpg.Connection, settings: WorkSettings,
    user_id: int, leave_type: str, start: str, end: str,
    status: str, reviewer_id: int | None, review_note: str | None,
    created_at, reviewed_at,
) -> None:
    hours = calculate_leave_hours(start, end, settings, _TZ)
    record = await leave_request_repository.create(
        conn, user_id, leave_type, start, end, hours, "展示用申請", created_at
    )
    if status != "pending":
        await leave_request_repository.update_review(
            conn, record["id"], status, reviewer_id, review_note, reviewed_at
        )


async def _seed_overtime_request(
    conn: asyncpg.Connection, settings: WorkSettings,
    user_id: int, start, end,
    status: str, reviewer_id: int | None, review_note: str | None,
    created_at, reviewed_at,
) -> None:
    hours = calculate_overtime_hours(start, end, settings, _TZ)
    record = await overtime_request_repository.create(conn, user_id, start, end, hours, "當日交付前加班處理", created_at)
    if status != "pending":
        await overtime_request_repository.update_review(
            conn, record["id"], status, reviewer_id, review_note, reviewed_at
        )


async def _seed_punch_request(
    conn: asyncpg.Connection,
    user_id: int, punch_type: str, target_date: date,
    requested_in_time, requested_out_time, reason: str,
    status: str, reviewer_id: int | None, review_note: str | None,
    created_at, reviewed_at,
) -> None:
    record = await punch_request_repository.create(
        conn, user_id, punch_type, target_date, requested_in_time, requested_out_time, reason, created_at
    )
    if status != "pending":
        await punch_request_repository.update_review(
            conn, record["id"], status, reviewer_id, review_note, reviewed_at
        )


async def seed_business_data(conn: asyncpg.Connection) -> None:
    settings = WorkSettings.from_row(await settings_repository.get_settings(conn))
    now = _at(date(2026, 8, 24), "09:00")

    # ---- 出勤：上週（08/17～08/21）示範資料 ----
    await _seed_attendance(conn, settings, now, EMPLOYEE_ID, date(2026, 8, 17), "09:03", "18:10")
    await _seed_attendance(conn, settings, now, EMPLOYEE_ID, date(2026, 8, 18), "09:22", "18:15")
    # 08/19 是陳小華的整天特別休假，刻意不建出勤列（見下方請假申請）。
    await _seed_attendance(conn, settings, now, EMPLOYEE_ID, date(2026, 8, 20), "08:58", "18:10")
    await _seed_attendance(conn, settings, now, EMPLOYEE_ID, date(2026, 8, 21), None, None)  # 曠職示範

    await _seed_attendance(conn, settings, now, OTHER_EMPLOYEE_ID, date(2026, 8, 17), "09:01", "18:02")
    await _seed_attendance(conn, settings, now, OTHER_EMPLOYEE_ID, date(2026, 8, 19), "09:30", "18:35")
    await _seed_attendance(conn, settings, now, OTHER_EMPLOYEE_ID, date(2026, 8, 21), "09:00", None)  # 未打下班卡示範

    # ---- 請假：涵蓋已核准／待審／已駁回三種狀態 ----
    await _seed_leave_request(
        conn, settings, EMPLOYEE_ID, "特別休假",
        _at(date(2026, 8, 19), "09:00"), _at(date(2026, 8, 19), "18:00"),
        status="approved", reviewer_id=MANAGER_ID, review_note=None,
        created_at=_at(date(2026, 8, 15), "10:00"), reviewed_at=_at(date(2026, 8, 15), "14:00"),
    )
    await _seed_leave_request(
        conn, settings, OTHER_EMPLOYEE_ID, "事假",
        _at(date(2026, 8, 27), "09:00"), _at(date(2026, 8, 27), "18:00"),
        status="pending", reviewer_id=None, review_note=None,
        created_at=_at(date(2026, 8, 21), "16:00"), reviewed_at=None,
    )
    await _seed_leave_request(
        conn, settings, 6, "病假",
        _at(date(2026, 8, 18), "09:00"), _at(date(2026, 8, 18), "13:00"),
        status="rejected", reviewer_id=ADMIN_ID, review_note="請補上就醫證明後重新申請",
        created_at=_at(date(2026, 8, 17), "20:00"), reviewed_at=_at(date(2026, 8, 18), "09:30"),
    )

    # ---- 加班：起始時間一律呼叫 compute_overtime_eligible_start() 算出，
    # 不得寫死（docs/PITFALLS.md E1 的原始事故就是這裡）----
    employee_overtime_day = date(2026, 8, 20)
    employee_eligible_start = compute_overtime_eligible_start(
        _at(employee_overtime_day, "08:58"), employee_overtime_day, settings, _TZ,
    )
    await _seed_overtime_request(
        conn, settings, EMPLOYEE_ID,
        employee_eligible_start, employee_eligible_start + timedelta(hours=2),
        status="approved", reviewer_id=MANAGER_ID, review_note=None,
        created_at=_at(employee_overtime_day, "21:00"), reviewed_at=_at(date(2026, 8, 21), "09:00"),
    )

    other_overtime_day = date(2026, 8, 17)
    other_eligible_start = compute_overtime_eligible_start(
        _at(other_overtime_day, "09:01"), other_overtime_day, settings, _TZ,
    )
    await _seed_overtime_request(
        conn, settings, OTHER_EMPLOYEE_ID,
        other_eligible_start, other_eligible_start + timedelta(hours=1, minutes=30),
        status="pending", reviewer_id=None, review_note=None,
        created_at=_at(other_overtime_day, "21:00"), reviewed_at=None,
    )

    # ---- 補打卡：已核准（示範「已異動」）＋ 待審（示範審核中心待辦） ----
    await _seed_punch_request(
        conn, EMPLOYEE_ID, "in", date(2026, 8, 18), _at(date(2026, 8, 18), "09:05"), None,
        "忘記正常打卡，實際準時到班",
        status="approved", reviewer_id=MANAGER_ID, review_note=None,
        created_at=_at(date(2026, 8, 19), "09:00"), reviewed_at=_at(date(2026, 8, 19), "10:00"),
    )
    await _seed_punch_request(
        conn, OTHER_EMPLOYEE_ID, "out", date(2026, 8, 21), None, _at(date(2026, 8, 21), "18:30"),
        "加班後忘記打下班卡",
        status="pending", reviewer_id=None, review_note=None,
        created_at=_at(date(2026, 8, 22), "09:00"), reviewed_at=None,
    )

    # ---- 場地預約：展示視窗（08/24～08/31）內，彼此不重疊 ----
    await room_booking_repository.create(
        conn, MANAGER_ID, 1, "部門週會", _at(date(2026, 8, 24), "10:00"), _at(date(2026, 8, 24), "11:00"),
    )
    await room_booking_repository.create(
        conn, EMPLOYEE_ID, 3, "新人教育訓練", _at(date(2026, 8, 26), "14:00"), _at(date(2026, 8, 26), "16:00"),
    )
    await room_booking_repository.create(
        conn, OTHER_MANAGER_ID, 2, "業務部晨會", _at(date(2026, 8, 27), "09:30"), _at(date(2026, 8, 27), "10:30"),
    )
