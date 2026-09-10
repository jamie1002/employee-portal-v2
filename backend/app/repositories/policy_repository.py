"""`policy_embeddings` 的全部 SQL。repository 不做授權判斷（範圍限縮是 service 的責任），
批 A 本來就是全域唯讀語料，這裡沒有任何範圍限縮需求。

向量參數一律以 `$N::text::vector` 轉型傳遞，**不**在連線池的 `_init_connection` 註冊
pgvector codec（見 `openspec/changes/add-policy-chat/design.md` Decision 3）：註冊
codec 會讓每一條池連線在建立時就依賴 `vector` 型別存在，若正式資料庫還沒跑過 migration，
會讓 `init_pool()` 整個入口網站起不來，而不只是 AI 助理壞掉。改用 text cast 後，
失敗面被限制在單一端點，且完全不需要 `pgvector` 這個 Python 套件。
"""

from __future__ import annotations

import asyncpg


def _vector_literal(vector: list[float]) -> str:
    """把向量序列化成 pgvector 的文字表示法（例："[0.1,0.2,0.3]"），供 `::vector` 轉型使用。"""
    return "[" + ",".join(repr(value) for value in vector) + "]"


async def find_existing_hashes(pool: asyncpg.Pool) -> dict[tuple[str, int], str]:
    """回傳現有每個 chunk 的 content_hash，供 ingest 判斷內容是否變更。"""
    rows = await pool.fetch("SELECT source_file, chunk_index, content_hash FROM policy_embeddings")
    return {(row["source_file"], row["chunk_index"]): row["content_hash"] for row in rows}


async def upsert_chunk(
    pool: asyncpg.Pool,
    source_file: str,
    chunk_index: int,
    section_path: str,
    content: str,
    raw_content: str,
    content_hash: str,
    embedding: list[float],
) -> None:
    """新增或更新單一 chunk。ingest 只對內容有變更的 chunk 呼叫本函式（見 policy_ingest.py），
    這裡的 UPSERT 一律覆蓋全部欄位——沒有「部分更新保留舊值」的需求，呼叫端每次都會提供
    完整內容。"""
    await pool.execute(
        f"""
        INSERT INTO policy_embeddings
            (source_file, chunk_index, section_path, content, raw_content, content_hash, embedding)
        VALUES ($1, $2, $3, $4, $5, $6, $7::text::vector)
        ON CONFLICT (source_file, chunk_index) DO UPDATE SET
            section_path = EXCLUDED.section_path,
            content      = EXCLUDED.content,
            raw_content  = EXCLUDED.raw_content,
            content_hash = EXCLUDED.content_hash,
            embedding    = EXCLUDED.embedding,
            updated_at   = now()
        """,
        source_file,
        chunk_index,
        section_path,
        content,
        raw_content,
        content_hash,
        _vector_literal(embedding),
    )


async def delete_orphans(pool: asyncpg.Pool, keys: list[tuple[str, int]]) -> int:
    """刪除語料中已不存在的 (source_file, chunk_index)。回傳實際刪除筆數。"""
    if not keys:
        return 0
    result = await pool.executemany(
        "DELETE FROM policy_embeddings WHERE source_file = $1 AND chunk_index = $2",
        keys,
    )
    # asyncpg 的 executemany 不像 execute 回傳 "DELETE n"，用 keys 長度作為刪除筆數——
    # 每個 key 在唯一約束下最多對應一列，len(keys) 即為實際刪除數。
    del result
    return len(keys)


async def search_similar(pool: asyncpg.Pool, query_vector: list[float], top_k: int) -> list[dict]:
    """依餘弦相似度排序回傳前 top_k 筆，**不套用門檻過濾**——過濾是 service 層
    （`policy_retrieval.py`）的責任，repository 只負責排序與筆數上限。"""
    rows = await pool.fetch(
        """
        SELECT source_file, section_path, content,
               1 - (embedding <=> $1::text::vector) AS score
        FROM policy_embeddings
        ORDER BY embedding <=> $1::text::vector
        LIMIT $2
        """,
        _vector_literal(query_vector),
        top_k,
    )
    return [dict(row) for row in rows]


async def count(pool: asyncpg.Pool) -> int:
    """語料筆數，供 `/api/health` 顯示——雲端 ingest 忘了跑時，看一眼就知道（見
    design.md 風險 7：忘了 ingest 是靜默失敗，表是空的但助理看起來運作正常）。"""
    return await pool.fetchval("SELECT count(*) FROM policy_embeddings")
