"""通用滑動視窗限流。行程記憶體、`time.monotonic()`。

**不用虛擬時鐘**：虛擬時間到達 clamp 上限（2026-08-31）後就不再前進，限流視窗永遠不會
滑動，展示環境的虛擬時鐘一旦走到視窗末端，所有使用者都會被永久鎖在限流狀態且無法自行
恢復——與 `docs/PITFALLS.md` B4（閒置重置計時器）是同一個失敗模式。
**不用 Redis**：單一實例的展示站不值得多引入一個服務。

刻意不在這裡耦合任何業務錯誤碼——回傳布林值，由呼叫端（例如 `services/chat.py`）決定
超過限制時要拋出什麼 `AppError`，讓批 B 的工具查詢也能重用同一支函式、配自己的錯誤碼。
"""

from __future__ import annotations

import time
from collections import defaultdict

_WINDOW_SECONDS = 60.0

_hits: dict[str, list[float]] = defaultdict(list)


def check_and_record(key: str, limit: int, window_seconds: float = _WINDOW_SECONDS) -> bool:
    """檢查並記錄一次呼叫。回傳 `True` 表示本次在限制內（已記錄這次呼叫）；
    回傳 `False` 表示 `key` 在過去 `window_seconds` 秒內已達 `limit` 次（不記錄本次）。"""
    now = time.monotonic()
    window_start = now - window_seconds
    timestamps = [timestamp for timestamp in _hits[key] if timestamp > window_start]

    if len(timestamps) >= limit:
        _hits[key] = timestamps
        return False

    timestamps.append(now)
    _hits[key] = timestamps
    return True
