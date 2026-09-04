"""展示用虛擬時鐘。

get_virtual_now() = clamp(virtual_anchor + (真實現在 − real_anchor), 2026-08-24, 2026-08-31)
——虛擬時鐘會跟著真實時間持續走動，不是停在設定的那一刻（見 SPEC.md §4.10）。

所有業務時間戳一律取自這裡，禁止用 datetime.now()、SQL 的 now() 或資料庫觸發器。
**唯一例外**：展示資料閒置自動重置的計時器刻意用真實時間（time.monotonic()）——
虛擬時間到達 clamp 上限後就不再前進，用它會讓重置機制永遠不觸發（見 docs/PITFALLS.md B4）。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config.database import get_pool

_TZ = ZoneInfo("Asia/Taipei")
_CLAMP_MIN = datetime(2026, 8, 24, 0, 0, 0, tzinfo=_TZ)
_CLAMP_MAX = datetime(2026, 8, 31, 23, 59, 59, tzinfo=_TZ)


def _clamp(moment: datetime) -> datetime:
    if moment < _CLAMP_MIN:
        return _CLAMP_MIN
    if moment > _CLAMP_MAX:
        return _CLAMP_MAX
    return moment


async def get_virtual_now() -> datetime:
    pool = get_pool()
    row = await pool.fetchrow("SELECT real_anchor, virtual_anchor FROM demo_clock WHERE id = 1")
    real_anchor: datetime = row["real_anchor"]
    virtual_anchor: datetime = row["virtual_anchor"]
    elapsed = datetime.now(tz=real_anchor.tzinfo) - real_anchor
    return _clamp(virtual_anchor + elapsed)


async def set_virtual_clock(new_virtual_now: datetime) -> datetime:
    """使用者調整虛擬時鐘：換算出新的 (real_anchor, virtual_anchor) 配對，
    調整後虛擬時鐘依然會跟著真實時間繼續走動，不是停在設定的那一刻。
    超出展示視窗自動 clamp 回邊界，不報錯（見 SPEC.md §4.10）。"""
    pool = get_pool()
    real_now = datetime.now(tz=ZoneInfo("UTC"))
    clamped = _clamp(new_virtual_now)
    await pool.execute(
        """
        UPDATE demo_clock
        SET real_anchor = $1, virtual_anchor = $2, updated_at = now()
        WHERE id = 1
        """,
        real_now,
        clamped,
    )
    return clamped
