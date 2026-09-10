"""檢索服務：把使用者的查詢轉成向量，對 `policy_embeddings` 檢索最相似的 chunk，
並套用 `RETRIEVAL_MIN_SCORE` 門檻過濾。

過濾後為空時回傳空 list：要不要回覆「文件中查無相關規定」是上層（`services/chat.py`）
的措辭決定，這裡只負責「有沒有足夠相關的依據」這件事。
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from app.config.settings import app_settings
from app.repositories import policy_repository
from app.utils.gemini import GeminiClient


@dataclass
class RetrievalResult:
    """一筆檢索結果。"""

    source_file: str
    section_path: str
    content: str
    score: float
    """餘弦相似度，範圍 [-1, 1]，越大越相似。"""


async def retrieve(pool: asyncpg.Pool, client: GeminiClient, question: str) -> list[RetrievalResult]:
    """對 `question` 執行一次檢索，回傳依相似度排序、且已套用 `RETRIEVAL_MIN_SCORE`
    門檻過濾（`>=`，等於門檻視為保留）的結果。"""
    vector = await client.embed_query(question)
    rows = await policy_repository.search_similar(pool, vector, app_settings.RETRIEVAL_TOP_K)
    results = [RetrievalResult(**row) for row in rows]
    return [result for result in results if result.score >= app_settings.RETRIEVAL_MIN_SCORE]
