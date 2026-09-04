"""手刻請求驗證的共用小工具。

一律回傳**原生 Python 物件**（`datetime.date` 等）而非字串——asyncpg 對 DATE／
TIMESTAMPTZ 參數要求原生型別，在驗證這一層就轉好，後面每一層都不必再猜
（見 docs/PITFALLS.md A5）。
"""

from datetime import date, datetime

from app.utils.errors import AppError


def validation_error(message: str) -> AppError:
    return AppError(400, message, "VALIDATION_ERROR")


def parse_date_str(params: dict, key: str) -> date:
    raw = params.get(key)
    if raw is None or raw == "":
        raise validation_error(f"{key} 為必填")
    return _to_date(raw, key)


def parse_optional_date_str(params: dict, key: str) -> date | None:
    raw = params.get(key)
    if raw is None or raw == "":
        return None
    return _to_date(raw, key)


def parse_optional_positive_int(raw, message: str) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise validation_error(message) from None
    if value < 1:
        raise validation_error(message)
    return value


def parse_int_in_range(raw, key: str, default: int, minimum: int, maximum: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise validation_error(f"{key} 格式不正確") from None
    if value < minimum or value > maximum:
        raise validation_error(f"{key} 必須介於 {minimum} 到 {maximum} 之間")
    return value


def require_str(data: dict, key: str, message: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise validation_error(message)
    return value.strip()


def parse_datetime_field(data: dict, key: str) -> datetime:
    """一律要求帶時區資訊的 ISO 字串（前端固定送 `+08:00`），拒絕 naive 字串——
    否則後續與其他一律帶時區的 datetime 比較會直接拋型別錯誤。"""
    raw = data.get(key)
    if not isinstance(raw, str) or not raw:
        raise validation_error(f"{key} 為必填")
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        raise validation_error(f"{key} 格式不正確") from None
    if value.tzinfo is None:
        raise validation_error(f"{key} 必須包含時區資訊")
    return value


def parse_optional_datetime_field(data: dict, key: str) -> datetime | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return parse_datetime_field(data, key)


def _to_date(raw, key: str) -> date:
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise validation_error(f"{key} 格式不正確，須為 YYYY-MM-DD") from None
