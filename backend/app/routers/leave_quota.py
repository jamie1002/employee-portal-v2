"""假別配額查詢端點。"""

from fastapi import APIRouter, Depends

from app.config.database import get_pool
from app.config.settings import app_settings
from app.middleware.auth import get_current_user
from app.repositories import user_repository
from app.services import leave_quota as leave_quota_service
from app.utils.timezone import get_business_date
from app.utils.virtual_clock import get_virtual_now

router = APIRouter()


@router.get("/leave-quota/me")
async def get_mine(current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    user = await user_repository.find_public_by_id(pool, current_user["id"])
    today = get_business_date(await get_virtual_now(), tz=app_settings.APP_TIMEZONE)
    quota = await leave_quota_service.get_my_leave_quota(pool, user, today)
    return {"quota": quota}
