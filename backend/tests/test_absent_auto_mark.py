"""曠職自動標記排程（SPEC.md §4.1.8）。

排程器本身只負責「什麼時候跑」，這裡直接呼叫 job 的核心函式驗證業務行為。
"""

from datetime import date

from app.jobs.absent_auto_mark import run_absent_auto_mark
from app.utils.pg_types import pg_date
from app.utils.virtual_clock import set_virtual_clock
from tests.helpers import EMPLOYEE_ID, taipei


async def _absent_dates(db, user_id: int) -> list[date]:
    rows = await db.fetch(
        "SELECT punch_date FROM attendances WHERE user_id = $1 AND status = 'absent' ORDER BY punch_date",
        user_id,
    )
    return [row["punch_date"] for row in rows]


async def test_marks_past_workdays_without_any_record(client, db, pool):
    await set_virtual_clock(taipei(2026, 8, 26, 9, 0))  # 週三

    inserted = await run_absent_auto_mark(pool)

    assert inserted > 0
    dates = await _absent_dates(db, EMPLOYEE_ID)
    assert date(2026, 8, 24) in dates  # 週一
    assert date(2026, 8, 25) in dates  # 週二


async def test_does_not_mark_today_or_future_days(client, db, pool):
    await set_virtual_clock(taipei(2026, 8, 26, 9, 0))

    await run_absent_auto_mark(pool)

    dates = await _absent_dates(db, EMPLOYEE_ID)
    assert date(2026, 8, 26) not in dates
    assert date(2026, 8, 27) not in dates


async def test_skips_weekends_and_national_holidays(client, db, pool):
    await db.execute(
        "INSERT INTO holidays (holiday_date, name) VALUES ($1, '測試用假日') ON CONFLICT DO NOTHING",
        pg_date(date(2026, 8, 25)),
    )
    await set_virtual_clock(taipei(2026, 8, 31, 9, 0))  # 下週一

    await run_absent_auto_mark(pool)

    dates = await _absent_dates(db, EMPLOYEE_ID)
    assert date(2026, 8, 25) not in dates  # 國定假日
    assert date(2026, 8, 29) not in dates  # 週六
    assert date(2026, 8, 30) not in dates  # 週日
    assert date(2026, 8, 28) in dates  # 週五照常標記


async def test_does_not_touch_days_that_already_have_a_record(client, db, pool):
    await db.execute(
        """
        INSERT INTO attendances (user_id, punch_date, punch_in_time, status, created_at, updated_at)
        VALUES ($1, $2, $3, 'normal', now(), now())
        """,
        EMPLOYEE_ID,
        pg_date(date(2026, 8, 24)),
        taipei(2026, 8, 24, 9, 0),
    )
    await set_virtual_clock(taipei(2026, 8, 26, 9, 0))

    await run_absent_auto_mark(pool)

    status = await db.fetchval(
        "SELECT status FROM attendances WHERE user_id = $1 AND punch_date = $2",
        EMPLOYEE_ID,
        pg_date(date(2026, 8, 24)),
    )
    assert status == "normal"


async def test_running_twice_inserts_nothing_the_second_time(client, db, pool):
    await set_virtual_clock(taipei(2026, 8, 26, 9, 0))

    first = await run_absent_auto_mark(pool)
    second = await run_absent_auto_mark(pool)

    assert first > 0
    assert second == 0


async def test_does_not_mark_days_before_hire_date(client, db, pool):
    """李小芳（使用者 6）2026-06-01 到職，不該被標記到職前的曠職。"""
    await set_virtual_clock(taipei(2026, 8, 26, 9, 0))

    await run_absent_auto_mark(pool)

    earliest = await db.fetchval(
        "SELECT min(punch_date) FROM attendances WHERE user_id = 6 AND status = 'absent'"
    )
    assert earliest >= date(2026, 6, 1)
