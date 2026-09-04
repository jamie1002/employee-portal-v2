"""展示機制端點：虛擬時鐘與展示資料重置（SPEC.md §4.10 §4.11 §6.7）。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import get_current_user, require_roles
from app.schemas.common import parse_datetime_field
from app.services import demo as demo_service

router = APIRouter()


@router.get("/demo/clock")
async def get_clock(current_user: dict = Depends(get_current_user)):
    return await demo_service.get_clock_info()


@router.put("/demo/clock")
async def update_clock(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    new_virtual_now = parse_datetime_field(body, "virtual_now")
    return await demo_service.update_clock(new_virtual_now)


@router.post("/demo/reset")
async def reset(current_user: dict = Depends(require_roles("admin"))):
    counts = await demo_service.reset_demo_data(get_pool())
    return {"counts": counts}
