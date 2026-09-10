"""AI 政策問答測試共用工具（見 openspec/changes/add-policy-chat/design.md Decision 8）。

v2 禁止 mock 資料庫，本模組只提供「假 Gemini client」取代對外部 API 的 HTTP 呼叫，
所有 SQL 語意（相似度排序、門檻過濾、UPSERT、刪孤兒）仍打真實 PostgreSQL。

`make_unit_vector` 用「前幾維手工指定、其餘補 0 再正規化」的方式構造向量，讓餘弦相似度
可以被精確算出來——這樣 `RETRIEVAL_MIN_SCORE` 的邊界才測得到「剛好等於」與「差一點點」
兩種情況，不必依賴真實 embedding 的浮動分數碰運氣。
"""

from __future__ import annotations

import math

import pytest
import pytest_asyncio

from app.main import app
from app.routers.chat import get_chat_client
from app.services import rate_limit


def make_unit_vector(prefix: list[float], dim: int = 768) -> list[float]:
    vector = list(prefix) + [0.0] * (dim - len(prefix))
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


class FakeGeminiClient:
    """注入用的假 client，取代對 Gemini 的實際 HTTP 呼叫。"""

    def __init__(
        self,
        query_vector: list[float] | None = None,
        document_vectors: list[list[float]] | None = None,
        generate_text: str = "測試回答\n\n— 依據：test.md 測試 > 章節",
        generate_error: Exception | None = None,
    ) -> None:
        self.query_vector = query_vector if query_vector is not None else make_unit_vector([1.0])
        self.document_vectors = document_vectors or []
        self.generate_text = generate_text
        self.generate_error = generate_error
        self.embed_query_calls = 0
        self.embed_documents_calls = 0
        self.generate_calls = 0
        # 記錄每次 generate 收到的 (system_instruction, user_content)，讓測試能斷言
        # 落空路徑走的是受限的 FALLBACK_PROMPT 而不是政策問答的 SYSTEM_PROMPT——
        # 用錯 prompt 等於讓模型在沒有檢索依據的情況下談政策，是幻覺風險的來源。
        self.generate_calls_args: list[tuple[str, str]] = []

    async def embed_query(self, text: str) -> list[float]:
        self.embed_query_calls += 1
        return self.query_vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embed_documents_calls += 1
        if self.document_vectors:
            return self.document_vectors[: len(texts)]
        return [make_unit_vector([1.0]) for _ in texts]

    async def generate(self, system_instruction: str, user_content: str, tools=None) -> str:
        self.generate_calls += 1
        self.generate_calls_args.append((system_instruction, user_content))
        if self.generate_error is not None:
            raise self.generate_error
        return self.generate_text


@pytest.fixture
def use_fake_chat_client():
    """把 `/api/chat` 的 `get_chat_client` dependency 換成指定的假 client。"""

    def _apply(fake_client: FakeGeminiClient) -> None:
        app.dependency_overrides[get_chat_client] = lambda: fake_client

    yield _apply
    app.dependency_overrides.pop(get_chat_client, None)


@pytest_asyncio.fixture
async def clean_policy_embeddings(pool):
    """`policy_embeddings` 刻意不受 `reset_business_data`（種子重置）影響，需要語料
    隔離的測試自行清空，避免測試之間互相汙染。"""
    await pool.execute("DELETE FROM policy_embeddings")
    yield
    await pool.execute("DELETE FROM policy_embeddings")


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """`rate_limit._hits` 是行程級狀態，會跨測試持續累積——不重置的話，同一個種子
    使用者（例如 admin id=1）在多個測試函式裡累積呼叫次數，遲早會撞到
    `CHAT_RATE_LIMIT_PER_MINUTE` 而讓不相關的測試意外收到 429。"""
    rate_limit._hits.clear()
    yield
    rate_limit._hits.clear()
