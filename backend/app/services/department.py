"""部門管理的業務邏輯（SPEC.md §4.7）。"""

import asyncpg

from app.repositories import department_repository, user_repository
from app.utils.errors import AppError


async def _assert_valid_manager(pool: asyncpg.Pool, manager_id: int | None) -> None:
    if manager_id is None:
        return
    role = await user_repository.find_role_by_id(pool, manager_id)
    if role not in ("manager", "admin"):
        raise AppError(400, "部門主管必須具備 manager 或 admin 角色。", "INVALID_MANAGER_ROLE")


async def list_departments(pool: asyncpg.Pool) -> list[dict]:
    return [dict(row) for row in await department_repository.find_all(pool)]


async def create_department(pool: asyncpg.Pool, name: str, manager_id: int | None) -> dict:
    await _assert_valid_manager(pool, manager_id)
    new_id = await department_repository.create(pool, name, manager_id)
    return dict(await department_repository.find_by_id(pool, new_id))


async def update_department(pool: asyncpg.Pool, department_id: int, name: str, manager_id: int | None) -> dict:
    await _assert_valid_manager(pool, manager_id)
    if not await department_repository.update(pool, department_id, name, manager_id):
        raise AppError(404, "找不到指定的部門。", "NOT_FOUND")
    return dict(await department_repository.find_by_id(pool, department_id))


async def delete_department(pool: asyncpg.Pool, department_id: int) -> None:
    if not await department_repository.delete_by_id(pool, department_id):
        raise AppError(404, "找不到指定的部門。", "NOT_FOUND")
