"""展示資料閒置自動重置（SPEC.md §4.11）。

閒置計時器刻意使用真實時間 `time.monotonic()`，不用虛擬時鐘——虛擬時間到達
clamp 上限後就不再前進，用它會讓重置機制永遠不觸發，這是虛擬時鐘規則的
唯一例外（見 docs/PITFALLS.md B4）。「閒置」是行程級的單一時間戳，由
`main.py` 的活動追蹤中介層在每個請求（`/api/health` 除外）呼叫 `mark_activity()`
刷新，不分使用者、不落地資料庫。
"""

import time

import structlog

from app.config.database import get_pool
from app.config.settings import app_settings
from app.services import demo as demo_service

logger = structlog.get_logger()

CHECK_INTERVAL_SECONDS = 5 * 60

_last_activity_at = time.monotonic()


def mark_activity() -> None:
    global _last_activity_at
    _last_activity_at = time.monotonic()


def is_enabled() -> bool:
    return app_settings.ENVIRONMENT == "production" and app_settings.DEMO_RESET_IDLE_MINUTES > 0


async def check_idle_and_reset_job() -> None:
    """供 APScheduler 呼叫的進入點：只記錄結果與錯誤，不向外拋出例外。"""
    if not is_enabled():
        return

    idle_seconds = time.monotonic() - _last_activity_at
    idle_threshold_seconds = app_settings.DEMO_RESET_IDLE_MINUTES * 60
    if idle_seconds < idle_threshold_seconds:
        return

    try:
        await demo_service.reset_demo_data(get_pool())
        logger.info("展示資料閒置自動重置完成", idle_minutes=app_settings.DEMO_RESET_IDLE_MINUTES)
    except Exception:  # noqa: BLE001
        logger.exception("展示資料閒置自動重置失敗")
    finally:
        # 不論成功或失敗都刷新基準點，避免下一輪檢查（最快 5 分鐘後）馬上又觸發。
        mark_activity()
