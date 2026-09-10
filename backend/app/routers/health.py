"""健康檢查端點：驗證應用程式與資料庫連線皆正常，供部署平台與監控使用。"""

from fastapi import APIRouter

from app.config.database import get_pool
from app.repositories import policy_repository

router = APIRouter()


@router.get("/health")
async def health_check():
    pool = get_pool()
    try:
        await pool.fetchval("SELECT 1")
        database_status = "connected"
    except Exception:
        database_status = "disconnected"

    # AI 政策問答語料筆數：雲端部署後 Neon 忘了手動跑 ingest 是靜默失敗
    # （助理對每一題都回「查無相關規定」，看起來像功能正常但答不出來），
    # 這裡新增一個欄位讓上線後看一眼健康檢查就知道有沒有灌語料（見
    # openspec/changes/add-policy-chat/design.md 風險 7）。表或 extension
    # 不存在時容錯回 None，不影響健康檢查本身的判定。
    try:
        policy_chunk_count = await policy_repository.count(pool)
    except Exception:
        policy_chunk_count = None

    return {"status": "ok", "database": database_status, "policy_chunk_count": policy_chunk_count}
