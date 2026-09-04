"""認證端點：只負責解析請求、掛權限 dependency、呼叫 service。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import get_current_user
from app.schemas.auth import parse_change_password, parse_login
from app.services import auth_service

router = APIRouter()


@router.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    data = parse_login(body)
    return await auth_service.login(get_pool(), data["email"], data["password"])


@router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {"user": current_user}


@router.post("/auth/change-password")
async def change_password(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    data = parse_change_password(body)
    user = await auth_service.change_password(
        get_pool(), current_user["id"], data["old_password"], data["new_password"]
    )
    return {"user": user}
