"""員工／權限端點。

注意：所有 `/users/permissions`（GET）這類靜態路徑，一律定義在
`/users/{user_id}`（PUT／DELETE）這種動態路徑之前，避免日後新增的動態路徑
搶先比對到 "permissions" 當作 {user_id}（見 SPEC.md §6.5）。
"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import get_current_user, require_roles
from app.schemas.permissions import parse_set_permissions
from app.schemas.user import parse_create_user, parse_update_user, parse_user_query
from app.services import permission_service
from app.services import user as user_service

router = APIRouter()


@router.get("/users/permissions")
async def list_permissions(current_user: dict = Depends(require_roles("admin"))):
    return {"permissions": await permission_service.list_permissions(get_pool())}


@router.get("/users")
async def list_users(request: Request, current_user: dict = Depends(get_current_user)):
    parsed = parse_user_query(dict(request.query_params))
    return {"users": await user_service.list_users(get_pool(), parsed["department_id"])}


@router.post("/users", status_code=201)
async def create_user(request: Request, current_user: dict = Depends(require_roles("admin"))):
    body = await request.json()
    data = parse_create_user(body)
    user = await user_service.create_user(
        get_pool(), data["name"], data["email"], data["role"], data["department_id"], data["password"]
    )
    return {"user": user}


@router.put("/users/{user_id}/permissions")
async def set_permissions(user_id: int, request: Request, current_user: dict = Depends(require_roles("admin"))):
    body = await request.json()
    permissions = parse_set_permissions(body)
    result = await permission_service.set_user_permissions(get_pool(), user_id, permissions, current_user["id"])
    return {"permissions": result}


@router.put("/users/{user_id}")
async def update_user(user_id: int, request: Request, current_user: dict = Depends(require_roles("admin"))):
    body = await request.json()
    data = parse_update_user(body)
    user = await user_service.update_user(
        get_pool(),
        user_id,
        data["name"],
        data["email"],
        data["role"],
        data["department_id"],
        data["extension_number"],
        data["hire_date"],
    )
    return {"user": user}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, current_user: dict = Depends(require_roles("admin"))):
    await user_service.delete_user(get_pool(), user_id, current_user["id"])
    return {"message": "帳號已刪除"}
