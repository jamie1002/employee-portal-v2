"""APScheduler 排程器的啟停，由 app 的 lifespan 呼叫。

測試不會啟動排程（測試不跑 lifespan），需要驗證排程邏輯時直接呼叫 job 本身的
`run_absent_auto_mark(pool)`——排程器只負責「什麼時候跑」，不含任何業務規則。
"""

from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.jobs.absent_auto_mark import CHECK_INTERVAL_SECONDS, run_absent_auto_mark_job
from app.jobs.demo_auto_reset import CHECK_INTERVAL_SECONDS as DEMO_RESET_CHECK_INTERVAL_SECONDS
from app.jobs.demo_auto_reset import check_idle_and_reset_job

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
    # 閒置檢查不需要「啟動後立刻跑一次」——剛啟動就觸發重置沒有意義，讓它照
    # 正常的間隔排程即可。
    _scheduler.add_job(
        check_idle_and_reset_job,
        trigger=IntervalTrigger(seconds=DEMO_RESET_CHECK_INTERVAL_SECONDS),
        id="demo_idle_auto_reset",
        replace_existing=True,
    )
    _scheduler.start()
    return _scheduler


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
