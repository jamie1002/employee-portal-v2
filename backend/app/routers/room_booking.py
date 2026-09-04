"""場地預約端點：只負責解析請求、掛權限 dependency、呼叫 service。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.config.settings import app_settings
from app.middleware.auth import get_current_user, require_roles
from app.schemas.room_booking import parse_create_room_booking, parse_room_booking_query
from app.services import room_booking as room_booking_service

router = APIRouter()


@router.post("/room-bookings", status_code=201)
async def create(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    data = parse_create_room_booking(body, app_settings.APP_TIMEZONE)
    booking = await room_booking_service.create_booking(
        get_pool(),
        current_user["id"],
        data["room_id"],
        data["title"],
        data["start_time"],
        data["end_time"],
        app_settings.APP_TIMEZONE,
    )
    return {"booking": booking}


@router.get("/room-bookings")
async def list_bookings(request: Request, current_user: dict = Depends(get_current_user)):
    parsed = parse_room_booking_query(dict(request.query_params))
    bookings = await room_booking_service.list_bookings(
        get_pool(), parsed["date"], parsed["room_id"], parsed["status"]
    )
    return {"bookings": bookings}


@router.patch("/room-bookings/{booking_id}/cancel")
async def cancel(booking_id: int, current_user: dict = Depends(get_current_user)):
    booking = await room_booking_service.cancel_booking(get_pool(), booking_id, current_user)
    return {"booking": booking}


@router.delete("/room-bookings/{booking_id}")
async def force_release(booking_id: int, current_user: dict = Depends(require_roles("admin"))):
    await room_booking_service.force_release(get_pool(), booking_id)
    return {"ok": True}
