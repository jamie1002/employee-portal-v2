"""員工帳號管理的業務邏輯（SPEC.md §4.7 §3.3）。"""

import asyncpg

from app.config.settings import app_settings
from app.repositories import department_repository, user_repository
from app.utils.errors import AppError
from app.utils.password import hash_password
from app.utils.timezone import get_business_date
from app.utils.virtual_clock import get_virtual_now


async def _assert_department_exists(pool: asyncpg.Pool, department_id: int | None) -> None:
    if department_id is None:
        return
    if await department_repository.find_by_id(pool, department_id) is None:
        raise AppError(400, "指定的部門不存在。", "DEPARTMENT_NOT_FOUND")


async def _assert_single_admin_slot(pool: asyncpg.Pool, new_role: str, current_user_id: int | None) -> None:
    """新增／修改後若角色為 admin，系統只能有一位。修改既有 admin 本身（角色不變）
    不算「新增名額」，放行；deny-by-default：其餘一律視為新增名額擋下。"""
    if new_role != "admin":
        return
    admin_count = await user_repository.count_by_role(pool, "admin")
    if admin_count == 0:
        return
    if current_user_id is not None:
        current_role = await user_repository.find_role_by_id(pool, current_user_id)
        if current_role == "admin":
            return
    raise AppError(400, "系統僅允許一位管理者。", "SINGLE_ADMIN_ONLY")


async def _assert_not_last_admin(pool: asyncpg.Pool, user_id: int, new_role: str) -> None:
    if new_role == "admin":
        return
    current_role = await user_repository.find_role_by_id(pool, user_id)
    if current_role != "admin":
        return
    admin_count = await user_repository.count_by_role(pool, "admin")
    if admin_count <= 1:
        raise AppError(400, "不得變更最後一位管理者的角色。", "LAST_ADMIN_PROTECTED")


async def list_users(pool: asyncpg.Pool, department_id: int | None) -> list[dict]:
    return [dict(row) for row in await user_repository.find_all(pool, department_id)]


async def create_user(
    pool: asyncpg.Pool, name: str, email: str, role: str, department_id: int | None, password: str
) -> dict:
    await _assert_department_exists(pool, department_id)
    await _assert_single_admin_slot(pool, role, None)

    employee_no_year = get_business_date(await get_virtual_now(), app_settings.APP_TIMEZONE).year
    try:
        new_id = await user_repository.create(
            pool, name, email, hash_password(password), role, department_id, employee_no_year
        )
    except asyncpg.UniqueViolationError:
        raise AppError(409, "此電子郵件已被使用。", "EMAIL_ALREADY_EXISTS") from None

    return dict(await user_repository.find_public_by_id(pool, new_id))


async def update_user(
    pool: asyncpg.Pool,
    user_id: int,
    name: str,
    email: str,
    role: str,
    department_id: int | None,
    extension_number: str | None,
    hire_date,
) -> dict:
    await _assert_department_exists(pool, department_id)
    await _assert_not_last_admin(pool, user_id, role)
    await _assert_single_admin_slot(pool, role, user_id)

    try:
        updated = await user_repository.update(
            pool, user_id, name, email, role, department_id, extension_number, hire_date
        )
    except asyncpg.UniqueViolationError:
        raise AppError(409, "此電子郵件已被使用。", "EMAIL_ALREADY_EXISTS") from None

    if not updated:
        raise AppError(404, "找不到指定的使用者。", "NOT_FOUND")

    return dict(await user_repository.find_public_by_id(pool, user_id))


async def delete_user(pool: asyncpg.Pool, user_id: int, actor_id: int) -> None:
    if user_id == actor_id:
        raise AppError(400, "不得刪除自己的帳號。", "CANNOT_DELETE_SELF")

    if not await user_repository.delete_by_id(pool, user_id):
        raise AppError(404, "找不到指定的使用者。", "NOT_FOUND")
