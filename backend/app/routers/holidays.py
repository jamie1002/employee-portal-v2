"""國定假日端點（SPEC.md §6.6）。維護權限用 require_permission，讓
`holidays.manage` 持有者也能通過，不是寫死 require_roles("admin")。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import get_current_user, require_permission
from app.schemas.common import parse_date_str
from app.schemas.holiday import parse_create_holiday
from app.services import holiday as holiday_service

router = APIRouter()


@router.get("/holidays")
async def list_holidays(current_user: dict = Depends(get_current_user)):
    return {"holidays": await holiday_service.list_holidays(get_pool())}


@router.post("/holidays", status_code=201)
async def create_holiday(
    request: Request, current_user: dict = Depends(require_permission("holidays.manage"))
):
    body = await request.json()
    data = parse_create_holiday(body)
    holiday = await holiday_service.create_holiday(get_pool(), data["holiday_date"], data["name"])
    return {"holiday": holiday}


@router.delete("/holidays/{holiday_date}", status_code=204)
async def delete_holiday(
    holiday_date: str, current_user: dict = Depends(require_permission("holidays.manage"))
):
    parsed_date = parse_date_str({"holiday_date": holiday_date}, "holiday_date")
    await holiday_service.delete_holiday(get_pool(), parsed_date)
