"""Gemini SDK 的唯一封裝。app 內其他地方（services／repositories／routers）
一律呼叫這裡的 `GeminiClient`，不得直接 import `google.generativeai`。

見 `openspec/changes/add-policy-chat/design.md` Decision 1：探針結果 `google-genai`
未通過 Gate 1（`Requires-Dist: pydantic<3.0.0,>=2.12.5`，會把 v2 鎖定的
`pydantic==2.10.4` 往上推），實際採用官方已停止維護但版本相容的
`google-generativeai==0.8.6`。import 這個套件時會印出一句 `FutureWarning`，
是套件本身的棄用警告，不是本專案的程式錯誤（見 `docs/PITFALLS.md`）。批 B 或未來
升級，必須等 `google-genai` 放寬 `pydantic` 下限、或 v2 的鎖定版本本身升級之後
再重跑探針。

**兩個容易搞混的「不對稱」**：
1. **正規化必須兩側一致**——這裡 document 與 query 兩側都做 L2 正規化。Gemini
   截斷維度後的向量預設沒有正規化（768 維時 L2 約 0.59）。
2. **`task_type` 則是刻意不對稱**——文件端用 `retrieval_document`、查詢端用
   `retrieval_query`，這是 Google 官方建議的檢索用法。這與第 1 點的正規化不同，
   不是不一致的錯誤。
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

import google.generativeai as genai

from app.config.settings import app_settings

_TASK_TYPE_DOCUMENT = "retrieval_document"
_TASK_TYPE_QUERY = "retrieval_query"

_throttle_lock = asyncio.Lock()
_last_call_at = 0.0


class GeminiUnavailable(RuntimeError):
    """Gemini 呼叫在功能上不可用：未設定金鑰、逾時、維度不符、或任何上游例外。

    刻意是 `RuntimeError` 而非 `AppError`——呼叫端（router 的 `get_chat_client`
    dependency、`services/chat.py` 的 `ask()`）必須自己攔截並轉譯成
    `AppError(503, ..., "CHAT_UNAVAILABLE")`，否則會被 unhandled exception handler
    吃成未分類的 500。
    """


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _check_dimension(vector: list[float]) -> None:
    if len(vector) != app_settings.EMBEDDING_DIM:
        raise GeminiUnavailable(
            f"embedding 維度不符：模型實際輸出 {len(vector)} 維，"
            f"但 EMBEDDING_DIM 設定為 {app_settings.EMBEDDING_DIM} 維。換過模型或維度時，"
            "記得同步修改 .env 的 EMBEDDING_DIM、migration 的 vector(N)，並清空重灌整張表。"
        )


async def _throttle() -> None:
    """行程級 RPM 節流：確保呼叫間隔至少 60 / GEMINI_REQUESTS_PER_MINUTE 秒。

    免費層每分鐘請求數有上限，主動放慢呼叫節奏，寧可慢一點也不要撞 429 後在使用者的
    請求路徑上長時間重試。"""
    global _last_call_at
    rpm = app_settings.GEMINI_REQUESTS_PER_MINUTE
    if rpm <= 0:
        return
    min_interval = 60.0 / rpm
    async with _throttle_lock:
        now = time.monotonic()
        wait = _last_call_at + min_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_at = time.monotonic()


class GeminiClient:
    """單次請求可重用的 Gemini client。`generate()` 的 `tools` 參數是為批 B 的
    function calling 預留的位子，批 A 恆傳 `None`。"""

    def __init__(self) -> None:
        genai.configure(api_key=app_settings.GOOGLE_API_KEY)

    async def _with_timeout(self, coro: Any) -> Any:
        try:
            return await asyncio.wait_for(coro, timeout=app_settings.GEMINI_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise GeminiUnavailable("呼叫 Gemini API 逾時。") from exc
        except GeminiUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — 上游 SDK 例外一律視為服務不可用
            raise GeminiUnavailable(f"呼叫 Gemini API 失敗：{exc}") from exc

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """把一批文件片段轉成向量列表，順序與輸入的 texts 一一對應（一次批次呼叫）。"""
        if not texts:
            return []

        async def _call() -> list[list[float]]:
            await _throttle()
            response = await genai.embed_content_async(
                model=app_settings.EMBEDDING_MODEL,
                content=texts,
                task_type=_TASK_TYPE_DOCUMENT,
                output_dimensionality=app_settings.EMBEDDING_DIM,
            )
            return [_normalize(vector) for vector in response["embedding"]]

        vectors = await self._with_timeout(_call())
        for vector in vectors:
            _check_dimension(vector)
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """把使用者的查詢文字轉成向量。task_type 刻意與 embed_documents 不同。"""

        async def _call() -> list[float]:
            await _throttle()
            response = await genai.embed_content_async(
                model=app_settings.EMBEDDING_MODEL,
                content=text,
                task_type=_TASK_TYPE_QUERY,
                output_dimensionality=app_settings.EMBEDDING_DIM,
            )
            return _normalize(response["embedding"])

        vector = await self._with_timeout(_call())
        _check_dimension(vector)
        return vector

    async def generate(self, system_instruction: str, user_content: str, tools: Any = None) -> str:
        """呼叫生成模型，`temperature=0` 求輸出穩定。"""

        async def _call() -> str:
            await _throttle()
            model = genai.GenerativeModel(
                model_name=app_settings.GEMINI_MODEL,
                system_instruction=system_instruction,
            )
            response = await model.generate_content_async(
                user_content,
                generation_config=genai.types.GenerationConfig(temperature=0),
            )
            return response.text

        return await self._with_timeout(_call())


def get_gemini_client() -> GeminiClient:
    """惰性建構 client。沒有設定金鑰時直接拋 GeminiUnavailable，呼叫端負責轉譯。"""
    if not app_settings.chat_enabled:
        raise GeminiUnavailable("尚未設定 GOOGLE_API_KEY，AI 助理目前無法使用。")
    return GeminiClient()
