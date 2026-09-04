"""手刻的請求驗證函式。本專案不用 pydantic model 做請求驗證（見 CLAUDE.md 架構慣例）。"""

import re

from app.utils.errors import AppError

_PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def parse_login(body: dict) -> dict:
    email = body.get("email")
    password = body.get("password")
    if not isinstance(email, str) or not email.strip():
        raise AppError(400, "請輸入電子郵件。", "VALIDATION_ERROR")
    if not isinstance(password, str) or not password:
        raise AppError(400, "請輸入密碼。", "VALIDATION_ERROR")
    return {"email": email.strip(), "password": password}


def parse_change_password(body: dict) -> dict:
    old_password = body.get("oldPassword")
    new_password = body.get("newPassword")
    if not isinstance(old_password, str) or not old_password:
        raise AppError(400, "請輸入目前密碼。", "VALIDATION_ERROR")
    if not isinstance(new_password, str) or not _PASSWORD_PATTERN.match(new_password):
        raise AppError(400, "新密碼至少 8 碼，且需同時包含英文字母與數字。", "VALIDATION_ERROR")
    return {"old_password": old_password, "new_password": new_password}
