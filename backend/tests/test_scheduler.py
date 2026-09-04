"""排程器的掛載方式。

只驗證「什麼時候跑」，業務行為在 test_absent_auto_mark.py。這支測試存在的理由是
實測踩過的坑：用 IntervalTrigger 的 start_date 指定「從現在開始」不會讓它立刻執行，
第一次執行會被 ceil 進位成一整個間隔之後，而且完全不會報錯——排程看起來掛上去了，
log 卻一直沒有輸出。
"""

from datetime import datetime, timedelta, timezone

from app.jobs.absent_auto_mark import CHECK_INTERVAL_SECONDS
from app.jobs.scheduler import start_scheduler, stop_scheduler


async def test_absent_job_is_registered_and_runs_immediately_after_startup():
    scheduler = start_scheduler()
    try:
        job = scheduler.get_job("absent_auto_mark")

        assert job is not None
        assert job.next_run_time is not None
        assert job.next_run_time - datetime.now(timezone.utc) < timedelta(minutes=1)
    finally:
        await stop_scheduler()


async def test_absent_job_repeats_on_the_configured_interval():
    scheduler = start_scheduler()
    try:
        job = scheduler.get_job("absent_auto_mark")

        assert job.trigger.interval == timedelta(seconds=CHECK_INTERVAL_SECONDS)
    finally:
        await stop_scheduler()
