"""認證授權 dependency。

role、department_id、permissions 一律每個請求回資料庫重查，token payload 內的值
不被信任——這是「收回權限即時生效」的前提（見 CLAUDE.md 硬性規則、SPEC.md §3.2）。
"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.database import get_pool
from app.services.auth_service import get_current_user_dict
from app.utils.errors import AppError
from app.utils.jwt_utils import decode_access_token

# auto_error=False：缺少 token 時我們要回自訂的 401 UNAUTHORIZED，
# 不要 FastAPI 預設的 403。
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise AppError(401, "請先登入。", "UNAUTHORIZED")

    payload = decode_access_token(credentials.credentials)
    pool = get_pool()
    return await get_current_user_dict(pool, payload["id"])


def require_roles(*roles: str):
    """角色不符一律回 403。角色之間無階層，要同時允許必須明列。"""

    async def _dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in roles:
            raise AppError(403, "權限不足。", "FORBIDDEN")
        return current_user

    return _dependency


def require_permission(permission: str, roles: tuple[str, ...] = ("admin",)):
    """角色命中 roles、或持有 permission，任一即放行。

    兩種失敗回傳完全相同的訊息與 code，不揭露是哪一道擋下的（見 SPEC.md §3.2）。
    """

    async def _dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] in roles or permission in current_user.get("permissions", []):
            return current_user
        raise AppError(403, "權限不足。", "FORBIDDEN")

    return _dependency
