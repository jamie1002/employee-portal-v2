"""健康檢查端點：驗證應用程式與資料庫連線皆正常，供部署平台與監控使用。"""

from fastapi import APIRouter

from app.config.database import get_pool

router = APIRouter()


@router.get("/health")
async def health_check():
    pool = get_pool()
    try:
        await pool.fetchval("SELECT 1")
        database_status = "connected"
    except Exception:
        database_status = "disconnected"

    return {"status": "ok", "database": database_status}
