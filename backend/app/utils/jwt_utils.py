"""JWT 簽發與驗證。

payload 只放 `{id, role, department_id, iat, exp}`；role／department_id 僅供除錯參考，
**不被信任**——每個請求一律回資料庫重查最新值（見 SPEC.md §3.2、CLAUDE.md 硬性規則）。
"""

from datetime import datetime, timedelta, timezone
from typing import TypedDict

import jwt

from app.config.settings import app_settings
from app.utils.errors import AppError

_ALGORITHM = "HS256"


class TokenPayload(TypedDict):
    id: int
    role: str
    department_id: int | None
    iat: int
    exp: int


def create_access_token(user_id: int, role: str, department_id: int | None) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "id": user_id,
        "role": role,
        "department_id": department_id,
        "iat": now,
        "exp": now + timedelta(hours=app_settings.JWT_EXPIRES_IN_HOURS),
    }
    return jwt.encode(payload, app_settings.JWT_SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    try:
        return jwt.decode(token, app_settings.JWT_SECRET, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AppError(401, "登入憑證無效或已逾期，請重新登入。", "INVALID_TOKEN") from exc
