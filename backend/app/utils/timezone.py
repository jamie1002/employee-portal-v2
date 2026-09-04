"""時區工具。

所有「今天是哪一天」的判斷一律走 get_business_date()，禁止直接用 UTC 日期——
台灣時間 08:00 對應 UTC 前一日 00:00，用 UTC 日期會把早班打卡記到前一天，
並沿著 UNIQUE(user_id, punch_date) 污染補打卡的目標列（見 docs/PITFALLS.md B1）。
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def get_business_date(moment: datetime, tz: str = "Asia/Taipei") -> date:
    if moment.tzinfo is None:
        raise ValueError("get_business_date() 需要帶時區資訊的 datetime，禁止傳入 naive datetime。")
    return moment.astimezone(ZoneInfo(tz)).date()


def truncate_to_minute(moment: datetime) -> datetime:
    """所有時間規則的比較一律先截斷到分鐘，在每個接受時間參數的純函式入口就截斷，
    不依賴呼叫端記得先處理（見 docs/PITFALLS.md B2）。"""
    return moment.replace(second=0, microsecond=0)
