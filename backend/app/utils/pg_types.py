"""asyncpg 的型別邊界集中處理。

asyncpg 對 DATE／TIME／TIMESTAMPTZ 欄位的查詢參數要求原生 Python 物件
（datetime.date／time／datetime），傳字串不會自動轉、會直接拋型別錯誤
（見 docs/PITFALLS.md A5）。所有 repository 一律呼叫這裡的函式，不自行 parse。
"""

from datetime import date, datetime, time


def pg_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def pg_time(value: time | str) -> time:
    if isinstance(value, time):
        return value
    return time.fromisoformat(value)


def pg_timestamp(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
