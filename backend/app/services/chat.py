"""問答服務：限流 → 檢索 → 空則短路 → 生成 → 組回應。上游例外一律轉 `AppError(503)`。

`ask()` 收整包 `current_user` 而不是只收 `user_id`——批 B 的個人查詢需要 `role` 與
`department_id` 做 deny-by-default 範圍限縮（見
`openspec/changes/add-policy-chat/design.md`「為批 B 鋪路」）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import asyncpg
import structlog

from app.config.settings import app_settings
from app.services import chat_prompt, policy_retrieval, rate_limit
from app.utils.errors import AppError
from app.utils.gemini import GeminiClient, GeminiUnavailable

logger = structlog.get_logger()


@dataclass
class Source:
    source_file: str
    section_path: str
    score: float


@dataclass
class Answer:
    """`kind` 批 A 恆為 `"policy"`，是批 B 的分流欄位（見 design.md「為批 B 鋪路」）。"""

    kind: str
    text: str
    refused: bool
    sources: list[Source] = field(default_factory=list)


def _to_dict(answer: Answer) -> dict:
    return {
        "kind": answer.kind,
        "text": answer.text,
        "refused": answer.refused,
        "sources": [
            {"source_file": s.source_file, "section_path": s.section_path, "score": s.score}
            for s in answer.sources
        ],
    }


async def ask(pool: asyncpg.Pool, client: GeminiClient, current_user: dict, question: str) -> dict:
    rate_key = f"chat:{current_user['id']}"
    if not rate_limit.check_and_record(rate_key, app_settings.CHAT_RATE_LIMIT_PER_MINUTE):
        raise AppError(429, "提問太頻繁，請稍後再試。", "CHAT_RATE_LIMITED")

    started_at = time.monotonic()

    try:
        results = await policy_retrieval.retrieve(pool, client, question)

        if not results:
            answer = Answer(kind="policy", text=chat_prompt.NO_ANSWER_TEXT, refused=True, sources=[])
            _log(current_user["id"], question, answer, started_at)
            return _to_dict(answer)

        user_content = chat_prompt.build_user_content(results, question)
        text = await client.generate(chat_prompt.SYSTEM_PROMPT, user_content)
    except GeminiUnavailable as exc:
        logger.warning("chat_upstream_unavailable", user_id=current_user["id"], error=str(exc))
        raise AppError(503, "AI 助理目前無法使用，請稍後再試。", "CHAT_UNAVAILABLE") from exc
    except Exception as exc:  # noqa: BLE001 — 涵蓋資料庫層例外（例如表／extension 不存在）
        logger.warning("chat_upstream_error", user_id=current_user["id"], error=str(exc))
        raise AppError(503, "AI 助理目前無法使用，請稍後再試。", "CHAT_UNAVAILABLE") from exc

    answer = Answer(
        kind="policy",
        text=text,
        refused=chat_prompt.is_refusal(text),
        sources=[Source(r.source_file, r.section_path, r.score) for r in results],
    )
    _log(current_user["id"], question, answer, started_at)
    return _to_dict(answer)


def _log(user_id: int, question: str, answer: Answer, started_at: float) -> None:
    """不把提問全文寫進 log——只記 user_id、問題長度、命中數、是否拒答、耗時
    （見 design.md 風險 15：log 隱私）。"""
    logger.info(
        "chat_answered",
        user_id=user_id,
        question_length=len(question),
        source_count=len(answer.sources),
        refused=answer.refused,
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
    )
