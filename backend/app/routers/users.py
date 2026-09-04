"""員工／權限端點。

批 1 只實作權限下放（GET /users/permissions、PUT /users/{id}/permissions）；
員工 CRUD 留給批 5。

注意：GET /users/permissions 這個靜態路徑必須定義在任何 /users/{user_id} 動態
路徑之前，避免日後新增的動態路徑搶先比對到 "permissions" 當作 {user_id}。
"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import require_roles
from app.schemas.permissions import parse_set_permissions
from app.services import permission_service

router = APIRouter()


@router.get("/users/permissions")
async def list_permissions(current_user: dict = Depends(require_roles("admin"))):
    return {"permissions": await permission_service.list_permissions(get_pool())}


@router.put("/users/{user_id}/permissions")
async def set_permissions(user_id: int, request: Request, current_user: dict = Depends(require_roles("admin"))):
    body = await request.json()
    permissions = parse_set_permissions(body)
    result = await permission_service.set_user_permissions(get_pool(), user_id, permissions, current_user["id"])
    return {"permissions": result}
