"""請假申請端點：只負責解析請求、掛權限 dependency、呼叫 service。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import get_current_user, require_roles
from app.repositories import leave_request_repository
from app.schemas.request import parse_create_leave_request, parse_request_query
from app.services import leave_request as leave_request_service
from app.services import request_review as request_review_service
from app.utils.virtual_clock import get_virtual_now

router = APIRouter()


@router.post("/leave-requests", status_code=201)
async def create(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    data = parse_create_leave_request(body)
    now = await get_virtual_now()
    result = await leave_request_service.create(
        get_pool(), current_user["id"], data["leave_type"], data["start_time"], data["end_time"], data["reason"], now
    )
    return {"request": result}


@router.get("/leave-requests/me")
async def get_my_requests(request: Request, current_user: dict = Depends(get_current_user)):
    parsed = parse_request_query(dict(request.query_params))
    result = await leave_request_service.get_my_requests(get_pool(), current_user["id"], parsed["status"])
    return {"requests": result}


@router.get("/leave-requests/pending")
async def get_pending(current_user: dict = Depends(require_roles("manager", "admin"))):
    return {"requests": await leave_request_service.get_pending(get_pool(), current_user)}


@router.patch("/leave-requests/{request_id}/review")
async def review(
    request_id: int, request: Request, current_user: dict = Depends(require_roles("manager", "admin"))
):
    body = await request.json()
    result = await request_review_service.review_request(
        get_pool(), leave_request_repository, request_id, body.get("action"), body.get("review_note"), current_user
    )
    return {"request": result}
