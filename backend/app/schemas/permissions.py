"""手刻的請求驗證函式：權限整組取代。"""

from app.utils.constants import PERMISSION_KEYS
from app.utils.errors import AppError


def parse_set_permissions(body: dict) -> list[str]:
    permissions = body.get("permissions")
    if not isinstance(permissions, list) or not all(isinstance(p, str) for p in permissions):
        raise AppError(400, "permissions 必須是字串陣列。", "VALIDATION_ERROR")

    unique_permissions = list(dict.fromkeys(permissions))
    invalid = [p for p in unique_permissions if p not in PERMISSION_KEYS]
    if invalid:
        raise AppError(400, f"不支援的權限鍵：{', '.join(invalid)}。", "VALIDATION_ERROR")

    return unique_permissions
