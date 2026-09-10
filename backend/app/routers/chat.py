"""AI 政策問答端點（批 A）。router 不做業務判斷，只掛權限 dependency 與呼叫 service。"""

from fastapi import APIRouter, Depends, Request

from app.config.database import get_pool
from app.middleware.auth import get_current_user
from app.schemas.chat import parse_chat_request
from app.services import chat as chat_service
from app.utils.errors import AppError
from app.utils.gemini import GeminiClient, GeminiUnavailable, get_gemini_client

router = APIRouter()


async def get_chat_client() -> GeminiClient:
    """建構 Gemini client 的 dependency，方便測試以 `app.dependency_overrides` 注入假
    client。**容易漏的一點**：`get_gemini_client()` 拋的 `GeminiUnavailable` 是
    `RuntimeError` 不是 `AppError`，若不在這裡攔截轉譯，會被 unhandled exception
    handler 吃成未分類的 500——這裡就是那唯一的轉譯點。"""
    try:
        return get_gemini_client()
    except GeminiUnavailable as exc:
        raise AppError(503, str(exc), "CHAT_UNAVAILABLE") from exc


@router.post("/chat")
async def post_chat(
    request: Request,
    current_user: dict = Depends(get_current_user),
    client: GeminiClient = Depends(get_chat_client),
):
    body = await request.json()
    data = parse_chat_request(body)
    answer = await chat_service.ask(get_pool(), client, current_user, data["question"])
    return {"answer": answer}
