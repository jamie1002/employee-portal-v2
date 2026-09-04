"""資料庫檢視頁端點（admin 專用，SPEC.md §6.7）。"""

from fastapi import APIRouter, Depends

from app.config.database import get_pool
from app.middleware.auth import require_roles
from app.services import schema_info as schema_info_service

router = APIRouter()


@router.get("/admin/schema")
async def get_schema_overview(current_user: dict = Depends(require_roles("admin"))):
    return await schema_info_service.get_schema_overview(get_pool())


@router.get("/admin/schema/{table}/rows")
async def get_table_preview(table: str, current_user: dict = Depends(require_roles("admin"))):
    return {"rows": await schema_info_service.get_table_preview(get_pool(), table)}
