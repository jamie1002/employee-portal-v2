"""員工帳號的手刻請求驗證（SPEC.md §4.7）。"""

import re

from app.schemas.common import (
    parse_optional_date_str,
    parse_optional_positive_int,
    require_str,
    validation_error,
)

ROLES = ("admin", "manager", "employee")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LENGTH = 8


def _parse_email(data: dict) -> str:
    email = require_str(data, "email", "請輸入電子郵件")
    if not _EMAIL_RE.match(email):
        raise validation_error("電子郵件格式不正確")
    return email


def _parse_role(data: dict) -> str:
    role = data.get("role")
    if role not in ROLES:
        raise validation_error("角色必須是 admin、manager 或 employee")
    return role


def parse_create_user(data: dict) -> dict:
    name = require_str(data, "name", "請輸入姓名")
    email = _parse_email(data)
    role = _parse_role(data)
    department_id = parse_optional_positive_int(data.get("department_id"), "department_id 格式不正確")
    password = require_str(data, "password", "請輸入密碼")
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise validation_error(f"密碼至少需要 {_MIN_PASSWORD_LENGTH} 個字元")

    return {"name": name, "email": email, "role": role, "department_id": department_id, "password": password}


def parse_update_user(data: dict) -> dict:
    """員工編號不接受前端傳入（由資料庫序列產生）；extension_number／hire_date
    未傳入時交給 repository 用 COALESCE 保留原值，這裡回傳 None 代表「沒傳」。"""
    name = require_str(data, "name", "請輸入姓名")
    email = _parse_email(data)
    role = _parse_role(data)
    department_id = parse_optional_positive_int(data.get("department_id"), "department_id 格式不正確")

    extension_number = data.get("extension_number")
    if extension_number is not None:
        if not isinstance(extension_number, str) or len(extension_number) > 20:
            raise validation_error("分機號碼格式不正確")
        extension_number = extension_number.strip() or None

    hire_date = parse_optional_date_str(data, "hire_date")

    return {
        "name": name,
        "email": email,
        "role": role,
        "department_id": department_id,
        "extension_number": extension_number,
        "hire_date": hire_date,
    }


def parse_user_query(params: dict) -> dict:
    department_id = parse_optional_positive_int(params.get("department_id"), "department_id 格式不正確")
    return {"department_id": department_id}
