"""展示機制的業務邏輯：虛擬時鐘查詢／調整、展示資料重置（SPEC.md §4.10 §4.11）。"""

from datetime import datetime

import asyncpg

from app.db_scripts.seed import apply_demo_seed
from app.utils.virtual_clock import CLAMP_MAX, CLAMP_MIN, get_virtual_now, set_virtual_clock


async def get_clock_info() -> dict:
    return {"virtual_now": await get_virtual_now(), "min": CLAMP_MIN, "max": CLAMP_MAX}


async def update_clock(new_virtual_now: datetime) -> dict:
    await set_virtual_clock(new_virtual_now)
    return await get_clock_info()


async def reset_demo_data(pool: asyncpg.Pool) -> dict:
    """整個重置包在同一個交易內：種子資料若寫入失敗，連同前面的 TRUNCATE 一併
    回滾，不會留下「業務資料已清空、新資料沒寫進去」的半殘狀態。"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await apply_demo_seed(conn)
