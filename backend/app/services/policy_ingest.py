"""Ingest 服務：把 `db/policy_docs/` 語料切段、算 embedding，並寫入 `policy_embeddings`。

流程：
1. `chunk_all_documents()` 切段。
2. 對每個 chunk 的 `raw_content` 算 SHA-256，跟資料庫現有的 `content_hash` 比對。
3. **只對內容有變的 chunk 呼叫一次批次 `embed_documents`**（不逐筆呼叫）。
4. **刪除語料中已不存在的 chunk**：資料庫裡有、但這次切段結果沒有的
   `(source_file, chunk_index)` 一律視為孤兒，直接刪除。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import asyncpg

from app.repositories import policy_repository
from app.services.policy_chunking import Chunk, chunk_all_documents
from app.utils.gemini import GeminiClient


@dataclass
class IngestSummary:
    """單次 ingest 執行結果摘要，供 CLI 輸出與測試驗證用。"""

    per_source_counts: dict[str, int] = field(default_factory=dict)
    """本次語料切出的 chunk 數，依 source_file 分組。"""

    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0

    embedding_calls: int = 0
    """實際呼叫 `embed_documents()` 的次數（批次呼叫，非逐筆）。
    增量 ingest 若沒有任何內容變更，這裡應該是 0——用來驗證「跳過沒變更的 chunk」真的有生效。"""


def _content_hash(raw_content: str) -> str:
    """算 `raw_content` 的 SHA-256，供增量 ingest 判斷內容是否變更用。"""
    return hashlib.sha256(raw_content.encode("utf-8")).hexdigest()


async def run_ingest(pool: asyncpg.Pool, client: GeminiClient) -> IngestSummary:
    """執行一次完整的 ingest 流程，回傳本次異動摘要。"""
    chunks = chunk_all_documents()

    per_source_counts: dict[str, int] = {}
    for chunk in chunks:
        per_source_counts[chunk.source_file] = per_source_counts.get(chunk.source_file, 0) + 1

    existing_hashes = await policy_repository.find_existing_hashes(pool)
    new_keys = {(chunk.source_file, chunk.chunk_index) for chunk in chunks}

    to_upsert: list[tuple[Chunk, str]] = []  # (chunk, 新算出的 content_hash)
    skipped = 0

    for chunk in chunks:
        key = (chunk.source_file, chunk.chunk_index)
        new_hash = _content_hash(chunk.raw_content)
        if existing_hashes.get(key) == new_hash:
            skipped += 1
        else:
            to_upsert.append((chunk, new_hash))

    summary = IngestSummary(per_source_counts=per_source_counts, skipped=skipped)

    if to_upsert:
        vectors = await client.embed_documents([chunk.content for chunk, _ in to_upsert])
        summary.embedding_calls = 1

        for (chunk, content_hash), vector in zip(to_upsert, vectors):
            key = (chunk.source_file, chunk.chunk_index)
            is_update = key in existing_hashes
            await policy_repository.upsert_chunk(
                pool,
                chunk.source_file,
                chunk.chunk_index,
                chunk.section_path,
                chunk.content,
                chunk.raw_content,
                content_hash,
                vector,
            )
            if is_update:
                summary.updated += 1
            else:
                summary.inserted += 1

    orphan_keys = list(existing_hashes.keys() - new_keys)
    if orphan_keys:
        summary.deleted = await policy_repository.delete_orphans(pool, orphan_keys)

    return summary


def format_summary(summary: IngestSummary) -> str:
    """把 IngestSummary 整理成人類可讀的文字，供 CLI 輸出。"""
    lines = ["各來源檔案的 chunk 數（本次切段結果）："]
    for source_file in sorted(summary.per_source_counts):
        lines.append(f"  {source_file}: {summary.per_source_counts[source_file]}")
    lines.append(
        f"本次異動：新增 {summary.inserted}、更新 {summary.updated}、"
        f"刪除 {summary.deleted}、跳過 {summary.skipped}"
    )
    lines.append(f"embed_documents 呼叫次數：{summary.embedding_calls}")
    return "\n".join(lines)
