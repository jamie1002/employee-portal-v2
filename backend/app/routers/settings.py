"""考勤設定端點（SPEC.md §6.6）。維護權限用 require_permission，讓
`settings.manage` 持有者也能通過，不是寫死 require_roles("admin")。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import get_current_user, require_permission
from app.schemas.settings import parse_update_settings
from app.services import settings as settings_service

router = APIRouter()


@router.get("/settings")
async def get_settings(current_user: dict = Depends(get_current_user)):
    return {"settings": await settings_service.get_settings(get_pool())}


@router.put("/settings")
async def update_settings(
    request: Request, current_user: dict = Depends(require_permission("settings.manage"))
):
    body = await request.json()
    data = parse_update_settings(body)
    updated = await settings_service.update_settings(
        get_pool(),
        data["work_start_time"],
        data["work_end_time"],
        data["lunch_start_time"],
        data["lunch_end_time"],
        data["grace_period_minutes"],
    )
    return {"settings": updated}
