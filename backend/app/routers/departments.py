"""部門端點（SPEC.md §6.5）。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import require_roles
from app.schemas.department import parse_department_body
from app.services import department as department_service

router = APIRouter()


@router.get("/departments")
async def list_departments(current_user: dict = Depends(require_roles("admin", "manager"))):
    return {"departments": await department_service.list_departments(get_pool())}


@router.post("/departments", status_code=201)
async def create_department(request: Request, current_user: dict = Depends(require_roles("admin"))):
    body = await request.json()
    data = parse_department_body(body)
    department = await department_service.create_department(get_pool(), data["name"], data["manager_id"])
    return {"department": department}


@router.put("/departments/{department_id}")
async def update_department(
    department_id: int, request: Request, current_user: dict = Depends(require_roles("admin"))
):
    body = await request.json()
    data = parse_department_body(body)
    department = await department_service.update_department(
        get_pool(), department_id, data["name"], data["manager_id"]
    )
    return {"department": department}


@router.delete("/departments/{department_id}")
async def delete_department(department_id: int, current_user: dict = Depends(require_roles("admin"))):
    await department_service.delete_department(get_pool(), department_id)
    return {"message": "部門已刪除"}
