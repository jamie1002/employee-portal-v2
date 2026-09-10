"""`POST /api/chat` 契約、生成硬約束、降級、限流、重置隔離（SPEC.md §4.12）。"""

import asyncpg
import pytest

from app.config.settings import app_settings
from app.repositories import policy_repository
from app.services import chat_prompt, policy_retrieval
from tests.helpers import login_headers
from tests.helpers_chat import (  # noqa: F401 — _reset_rate_limit 需被 import 才會 autouse 生效
    FakeGeminiClient,
    _reset_rate_limit,
    clean_policy_embeddings,
    make_unit_vector,
    use_fake_chat_client,
)

__all__ = ["clean_policy_embeddings", "use_fake_chat_client", "_reset_rate_limit"]


async def _seed_one_matching_chunk(pool, query_vector):
    """插入一筆與 query_vector 完全相同方向（score=1.0）的 chunk，確保能通過任何合理門檻。"""
    await policy_repository.upsert_chunk(
        pool, "test.md", 0, "測試 > 章節", "【測試 > 章節】\n內容", "內容", "hash0", query_vector
    )


async def test_requires_auth(client):
    response = await client.post("/api/chat", json={"question": "測試問題"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_missing_question_returns_400(client, use_fake_chat_client):
    use_fake_chat_client(FakeGeminiClient())
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/chat", headers=headers, json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_blank_question_returns_400(client, use_fake_chat_client):
    use_fake_chat_client(FakeGeminiClient())
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/chat", headers=headers, json={"question": "   "})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_question_too_long_returns_400(client, use_fake_chat_client, monkeypatch):
    use_fake_chat_client(FakeGeminiClient())
    monkeypatch.setattr(app_settings, "CHAT_MAX_QUESTION_CHARS", 10)
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/chat", headers=headers, json={"question": "一二三四五六七八九十十一"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_empty_retrieval_uses_restricted_fallback_prompt(
    client, pool, use_fake_chat_client, clean_policy_embeddings
):
    """檢索落空時走受限的 FALLBACK_PROMPT，讓「早安」、情緒抱怨這類輸入能得到
    自然回應，而不是一句制式拒答。**關鍵斷言是「用的是哪一個 prompt」**：落空
    路徑沒有任何檢索依據，若誤用政策問答的 SYSTEM_PROMPT，模型就會在沒有依據的
    情況下談規定，那正是幻覺的來源。"""
    fake_client = FakeGeminiClient()  # policy_embeddings 為空，檢索結果必為空
    use_fake_chat_client(fake_client)
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/chat", headers=headers, json={"question": "早安"})

    assert response.status_code == 200
    body = response.json()["answer"]
    assert body["kind"] == "fallback"
    assert body["refused"] is True
    assert body["sources"] == []

    assert fake_client.generate_calls == 1
    system_instruction, _ = fake_client.generate_calls_args[0]
    assert system_instruction == chat_prompt.FALLBACK_PROMPT
    assert system_instruction != chat_prompt.SYSTEM_PROMPT


async def test_answer_prompt_includes_live_attendance_settings(
    client, pool, use_fake_chat_client, clean_policy_embeddings
):
    """推算的基準必須是系統即時生效的設定，不是語料寫死的預設值——admin 改過
    考勤設定之後，語料還停在 09:00／10 分鐘，模型若照語料推算就會給出錯誤答案。"""
    query_vector = make_unit_vector([1.0])
    await _seed_one_matching_chunk(pool, query_vector)
    fake_client = FakeGeminiClient(query_vector=query_vector)
    use_fake_chat_client(fake_client)

    admin_headers = await login_headers(client, "admin@demo.com")
    await client.put(
        "/api/settings",
        headers=admin_headers,
        json={
            "work_start_time": "08:30",
            "work_end_time": "17:30",
            "lunch_start_time": "12:30",
            "lunch_end_time": "13:30",
            "grace_period_minutes": 15,
        },
    )

    headers = await login_headers(client, "employee@demo.com")
    response = await client.post("/api/chat", headers=headers, json={"question": "幾點算遲到？"})

    assert response.status_code == 200
    _, user_content = fake_client.generate_calls_args[0]
    assert "08:30" in user_content
    assert "15 分鐘" in user_content


async def test_normal_response_includes_sources(client, pool, use_fake_chat_client, clean_policy_embeddings):
    query_vector = make_unit_vector([1.0])
    await _seed_one_matching_chunk(pool, query_vector)
    fake_client = FakeGeminiClient(query_vector=query_vector)
    use_fake_chat_client(fake_client)
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/chat", headers=headers, json={"question": "測試問題"})

    assert response.status_code == 200
    body = response.json()["answer"]
    assert body["kind"] == "policy"
    assert fake_client.generate_calls == 1
    assert len(body["sources"]) == 1
    assert body["sources"][0]["source_file"] == "test.md"
    assert body["sources"][0]["section_path"] == "測試 > 章節"


async def test_rate_limit_returns_429_and_is_isolated_per_user(
    client, pool, use_fake_chat_client, clean_policy_embeddings, monkeypatch
):
    monkeypatch.setattr(app_settings, "CHAT_RATE_LIMIT_PER_MINUTE", 1)
    use_fake_chat_client(FakeGeminiClient())
    employee_headers = await login_headers(client, "employee@demo.com")
    other_headers = await login_headers(client, "manager@demo.com")

    first = await client.post("/api/chat", headers=employee_headers, json={"question": "第一問"})
    second = await client.post("/api/chat", headers=employee_headers, json={"question": "第二問"})
    other_user = await client.post("/api/chat", headers=other_headers, json={"question": "第三問"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "CHAT_RATE_LIMITED"
    assert other_user.status_code == 200  # 不同使用者的配額互不影響


async def test_no_api_key_returns_503_not_500(client, monkeypatch):
    monkeypatch.setattr(app_settings, "GOOGLE_API_KEY", "")
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/chat", headers=headers, json={"question": "測試問題"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CHAT_UNAVAILABLE"


async def test_upstream_generate_error_returns_503_not_500(
    client, pool, use_fake_chat_client, clean_policy_embeddings
):
    query_vector = make_unit_vector([1.0])
    await _seed_one_matching_chunk(pool, query_vector)
    use_fake_chat_client(
        FakeGeminiClient(query_vector=query_vector, generate_error=RuntimeError("模擬上游逾時"))
    )
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/chat", headers=headers, json={"question": "測試問題"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CHAT_UNAVAILABLE"


async def test_database_error_returns_503_not_500(client, use_fake_chat_client, monkeypatch):
    """模擬 policy_embeddings 表／vector extension 不存在的情境：檢索層拋出資料庫例外，
    不得讓 unhandled exception handler 把它吃成未分類的 500。"""

    async def _raise_undefined_table(*args, **kwargs):
        raise asyncpg.exceptions.UndefinedTableError('relation "policy_embeddings" does not exist')

    monkeypatch.setattr(policy_retrieval, "retrieve", _raise_undefined_table)
    use_fake_chat_client(FakeGeminiClient())
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/chat", headers=headers, json={"question": "測試問題"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CHAT_UNAVAILABLE"


async def test_demo_reset_does_not_clear_policy_embeddings(client, pool, clean_policy_embeddings):
    await _seed_one_matching_chunk(pool, make_unit_vector([1.0]))
    before = await pool.fetchval("SELECT count(*) FROM policy_embeddings")
    assert before == 1

    admin_headers = await login_headers(client, "admin@demo.com")
    reset_response = await client.post("/api/demo/reset", headers=admin_headers)

    assert reset_response.status_code == 200
    after = await pool.fetchval("SELECT count(*) FROM policy_embeddings")
    assert after == 1
