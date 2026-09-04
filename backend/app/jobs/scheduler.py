"""APScheduler 排程器的啟停，由 app 的 lifespan 呼叫。

測試不會啟動排程（測試不跑 lifespan），需要驗證排程邏輯時直接呼叫 job 本身的
`run_absent_auto_mark(pool)`——排程器只負責「什麼時候跑」，不含任何業務規則。
"""

from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.jobs.absent_auto_mark import CHECK_INTERVAL_SECONDS, run_absent_auto_mark_job

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler()
    # 啟動後要**立刻先跑一次**，否則每次重新部署最多有 6 小時看不到曠職標記。
    #
    # 這件事只能靠 `next_run_time` 指定，不能靠 IntervalTrigger 的 `start_date`：
    # trigger 算第一次執行時間是 `start_date + ceil((now − start_date) / 間隔) × 間隔`，
    # 而 add_job 當下的 now 一定比 start_date 晚幾毫秒，ceil 就直接進位成一整個
    # 間隔——看起來像設定了「從現在開始」，實際上第一次執行是 6 小時後
    # （實測踩過：排程掛上去了、log 卻一直沒有任何輸出）。
    _scheduler.add_job(
        run_absent_auto_mark_job,
        trigger=IntervalTrigger(seconds=CHECK_INTERVAL_SECONDS),
        id="absent_auto_mark",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
    _scheduler.start()
    return _scheduler


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
