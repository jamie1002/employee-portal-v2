"""認證業務邏輯：登入、修改密碼。"""

import asyncpg

from app.repositories import user_repository
from app.utils.constants import DEMO_ACCOUNT_EMAILS
from app.utils.errors import AppError
from app.utils.jwt_utils import create_access_token
from app.utils.password import hash_password, verify_password


def _to_user_dict(row: asyncpg.Record) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "department_id": row["department_id"],
        "is_first_login": row["is_first_login"],
        "permissions": list(row["permissions"]),
    }


async def login(pool: asyncpg.Pool, email: str, password: str) -> dict:
    row = await user_repository.find_by_email(pool, email)

    # 帳號不存在與密碼錯誤回傳完全相同的訊息與 code，不洩漏是哪一種情況
    # （見 SPEC.md §7.2 INVALID_CREDENTIALS）。
    if row is None or not verify_password(password, row["password_hash"]):
        raise AppError(401, "電子郵件或密碼錯誤。", "INVALID_CREDENTIALS")

    token = create_access_token(row["id"], row["role"], row["department_id"])
    return {"token": token, "user": _to_user_dict(row)}


async def get_current_user_dict(pool: asyncpg.Pool, user_id: int) -> dict:
    row = await user_repository.find_by_id_with_permissions(pool, user_id)
    if row is None:
        raise AppError(401, "使用者不存在，請重新登入。", "USER_NOT_FOUND")
    return _to_user_dict(row)


async def change_password(pool: asyncpg.Pool, user_id: int, old_password: str, new_password: str) -> dict:
    row = await user_repository.find_credentials_by_id(pool, user_id)
    if row is None:
        raise AppError(401, "使用者不存在，請重新登入。", "USER_NOT_FOUND")

    if row["email"] in DEMO_ACCOUNT_EMAILS:
        raise AppError(403, "展示帳號的密碼固定，不可修改。", "DEMO_ACCOUNT_PASSWORD_LOCKED")

    if not verify_password(old_password, row["password_hash"]):
        raise AppError(401, "目前密碼不正確。", "INVALID_OLD_PASSWORD")

    if verify_password(new_password, row["password_hash"]):
        raise AppError(400, "新密碼不得與目前密碼相同。", "PASSWORD_UNCHANGED")

    await user_repository.update_password(pool, user_id, hash_password(new_password))
    return await get_current_user_dict(pool, user_id)
