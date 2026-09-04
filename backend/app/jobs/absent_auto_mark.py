"""曠職自動標記（SPEC.md §4.1.8）。

對每位使用者、每個工作日，若完全沒有出勤列就補一筆 `status='absent'` 的原始出勤
紀錄。刻意**不**排除「當天有請假／補打卡申請」的日期——`attendances` 只保存原始
打卡事實，是否請假、申請有沒有核准由讀取時的生效值解析另外判斷（SPEC.md §4.2）。
這裡的原始事實很單純：這個工作日完全沒有任何出勤列，就是沒來打卡。
"""

import asyncpg
import structlog

from app.config.database import get_pool
from app.config.settings import app_settings
from app.utils.pg_types import pg_date
from app.utils.timezone import get_business_date
from app.utils.virtual_clock import get_virtual_now

logger = structlog.get_logger()

# 只回溯 60 天，避免每次執行都全表掃描整個歷史。
LOOKBACK_DAYS = 60
CHECK_INTERVAL_SECONDS = 6 * 60 * 60

# 「今天」（$1）由呼叫端傳入虛擬時鐘算出的營業日，**不得改用 SQL 的 CURRENT_DATE**
# ——那是資料庫伺服器的真實日期，展示時鐘往前後調整後兩者會不一致。
_SQL = f"""
    INSERT INTO attendances (user_id, punch_date, status)
    SELECT u.id, d::date, 'absent'
    FROM users u
    CROSS JOIN LATERAL generate_series(
        GREATEST(u.hire_date, $1::date - {LOOKBACK_DAYS})::timestamp,
        ($1::date - 1)::timestamp,
        interval '1 day'
    ) AS d
    WHERE EXTRACT(ISODOW FROM d) < 6
      AND NOT EXISTS (SELECT 1 FROM holidays h WHERE h.holiday_date = d::date)
      AND NOT EXISTS (
          SELECT 1 FROM attendances a WHERE a.user_id = u.id AND a.punch_date = d::date
      )
    ON CONFLICT (user_id, punch_date) DO NOTHING
"""


async def run_absent_auto_mark(pool: asyncpg.Pool) -> int:
    """回傳新增的曠職紀錄筆數。"""
    today = get_business_date(await get_virtual_now(), tz=app_settings.APP_TIMEZONE)
    status = await pool.execute(_SQL, pg_date(today))
    return int(status.rsplit(" ", 1)[-1])


async def run_absent_auto_mark_job() -> None:
    """供 APScheduler 呼叫的進入點：只記錄結果與錯誤，不向外拋出例外——
    排程任務拋例外只會讓整個排程器安靜地少跑一個 job。"""
    try:
        count = await run_absent_auto_mark(get_pool())
        if count > 0:
            logger.info("曠職自動標記完成", inserted=count)
    except Exception as exc:  # noqa: BLE001
        logger.error("曠職自動標記失敗", error=str(exc))
