"""補打卡申請端點：只負責解析請求、掛權限 dependency、呼叫 service。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.config.settings import app_settings
from app.middleware.auth import get_current_user, require_roles
from app.repositories import punch_request_repository
from app.schemas.request import parse_create_punch_request, parse_request_query
from app.services import punch_request as punch_request_service
from app.services import request_review as request_review_service
from app.utils.virtual_clock import get_virtual_now

router = APIRouter()


@router.post("/punch-requests", status_code=201)
async def create(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    now = await get_virtual_now()
    data = parse_create_punch_request(body, now, app_settings.APP_TIMEZONE)
    result = await punch_request_service.create(
        get_pool(),
        current_user["id"],
        data["type"],
        data["target_date"],
        data["requested_in_time"],
        data["requested_out_time"],
        data["reason"],
        now,
    )
    return {"request": result}


@router.get("/punch-requests/me")
async def get_my_requests(request: Request, current_user: dict = Depends(get_current_user)):
    parsed = parse_request_query(dict(request.query_params))
    result = await punch_request_service.get_my_requests(get_pool(), current_user["id"], parsed["status"])
    return {"requests": result}


@router.get("/punch-requests/pending")
async def get_pending(current_user: dict = Depends(require_roles("manager", "admin"))):
    return {"requests": await punch_request_service.get_pending(get_pool(), current_user)}


@router.patch("/punch-requests/{request_id}/review")
async def review(
    request_id: int, request: Request, current_user: dict = Depends(require_roles("manager", "admin"))
):
    body = await request.json()
    result = await request_review_service.review_request(
        get_pool(), punch_request_repository, request_id, body.get("action"), body.get("review_note"), current_user
    )
    return {"request": result}
