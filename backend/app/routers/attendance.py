"""出勤端點：只負責解析請求、掛權限 dependency、呼叫 service。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import get_current_user, require_roles
from app.schemas.attendance import (
    parse_attendance_changes_query,
    parse_company_attendance_query,
    parse_my_attendance_query,
)
from app.services import attendance as attendance_service
from app.services import attendance_changes as attendance_changes_service

router = APIRouter()


# 打卡對象一律取自 token（current_user["id"]），刻意不解析請求主體中的任何 user_id。
@router.post("/attendance/punch-in", status_code=201)
async def punch_in(current_user: dict = Depends(get_current_user)):
    return {"attendance": await attendance_service.punch_in(get_pool(), current_user["id"])}


@router.post("/attendance/punch-out")
async def punch_out(current_user: dict = Depends(get_current_user)):
    return {"attendance": await attendance_service.punch_out(get_pool(), current_user["id"])}


@router.get("/attendance/today")
async def get_today(current_user: dict = Depends(get_current_user)):
    return {"attendance": await attendance_service.get_today(get_pool(), current_user["id"])}


# 無請求主體：備註文字由伺服器端寫死，不接受前端傳入內容。
@router.post("/attendance/today/note")
async def mark_today_note(current_user: dict = Depends(get_current_user)):
    return {"attendance": await attendance_service.mark_today_note(get_pool(), current_user["id"])}


# 查詢對象一律取自 token，刻意不解析 query 中的任何 user_id。
@router.get("/attendance/me")
async def get_my_records(request: Request, current_user: dict = Depends(get_current_user)):
    parsed = parse_my_attendance_query(dict(request.query_params))
    return await attendance_service.get_my_records(get_pool(), current_user["id"], **parsed)


# 出勤異動：本人一律可查自己、manager 限同部門、admin 不限，範圍判斷集中在
# service，所以這裡不掛 require_roles。
@router.get("/attendance/changes")
async def get_changes(request: Request, current_user: dict = Depends(get_current_user)):
    parsed = parse_attendance_changes_query(dict(request.query_params))
    changes = await attendance_changes_service.get_changes(get_pool(), current_user, **parsed)
    return {"changes": changes}


@router.get("/attendance")
async def get_all(request: Request, current_user: dict = Depends(require_roles("admin"))):
    parsed = parse_company_attendance_query(dict(request.query_params))
    return {"records": await attendance_service.get_all(get_pool(), **parsed)}
