"""ingest：增量比對 content_hash、批次 embedding、刪孤兒（SPEC.md §4.12 Requirement 1）。"""

from app.services import policy_ingest
from app.services.policy_chunking import Chunk
from tests.helpers_chat import FakeGeminiClient, clean_policy_embeddings, make_unit_vector

__all__ = ["clean_policy_embeddings"]  # 供 pytest 探索 fixture


def _two_chunks() -> list[Chunk]:
    return [
        Chunk(
            source_file="a.md",
            chunk_index=0,
            section_path="測試 > 1",
            raw_content="內容一",
            content="【測試 > 1】\n內容一",
        ),
        Chunk(
            source_file="a.md",
            chunk_index=1,
            section_path="測試 > 2",
            raw_content="內容二",
            content="【測試 > 2】\n內容二",
        ),
    ]


async def test_first_ingest_inserts_all_chunks_with_one_embedding_call(pool, monkeypatch, clean_policy_embeddings):
    monkeypatch.setattr(policy_ingest, "chunk_all_documents", lambda: _two_chunks())
    client = FakeGeminiClient(document_vectors=[make_unit_vector([1.0]), make_unit_vector([0.0, 1.0])])

    summary = await policy_ingest.run_ingest(pool, client)

    assert summary.inserted == 2
    assert summary.updated == 0
    assert summary.deleted == 0
    assert summary.embedding_calls == 1
    assert client.embed_documents_calls == 1
    count = await pool.fetchval("SELECT count(*) FROM policy_embeddings WHERE source_file = 'a.md'")
    assert count == 2


async def test_second_ingest_with_unchanged_content_skips_embedding(pool, monkeypatch, clean_policy_embeddings):
    monkeypatch.setattr(policy_ingest, "chunk_all_documents", lambda: _two_chunks())
    first_client = FakeGeminiClient(document_vectors=[make_unit_vector([1.0]), make_unit_vector([0.0, 1.0])])
    await policy_ingest.run_ingest(pool, first_client)

    second_client = FakeGeminiClient()
    summary = await policy_ingest.run_ingest(pool, second_client)

    assert summary.inserted == 0
    assert summary.updated == 0
    assert summary.skipped == 2
    assert summary.embedding_calls == 0
    assert second_client.embed_documents_calls == 0


async def test_changed_chunk_is_updated_and_reembedded(pool, monkeypatch, clean_policy_embeddings):
    monkeypatch.setattr(policy_ingest, "chunk_all_documents", lambda: _two_chunks())
    first_client = FakeGeminiClient(document_vectors=[make_unit_vector([1.0]), make_unit_vector([0.0, 1.0])])
    await policy_ingest.run_ingest(pool, first_client)

    changed = _two_chunks()
    changed[0].raw_content = "內容一（已修改）"
    changed[0].content = "【測試 > 1】\n內容一（已修改）"
    monkeypatch.setattr(policy_ingest, "chunk_all_documents", lambda: changed)
    second_client = FakeGeminiClient(document_vectors=[make_unit_vector([1.0, 1.0])])

    summary = await policy_ingest.run_ingest(pool, second_client)

    assert summary.updated == 1
    assert summary.inserted == 0
    assert summary.skipped == 1
    assert summary.embedding_calls == 1


async def test_removed_section_deletes_orphan_chunk(pool, monkeypatch, clean_policy_embeddings):
    monkeypatch.setattr(policy_ingest, "chunk_all_documents", lambda: _two_chunks())
    first_client = FakeGeminiClient(document_vectors=[make_unit_vector([1.0]), make_unit_vector([0.0, 1.0])])
    await policy_ingest.run_ingest(pool, first_client)

    monkeypatch.setattr(policy_ingest, "chunk_all_documents", lambda: _two_chunks()[:1])
    second_client = FakeGeminiClient()

    summary = await policy_ingest.run_ingest(pool, second_client)

    assert summary.deleted == 1
    remaining = await pool.fetchval("SELECT count(*) FROM policy_embeddings WHERE source_file = 'a.md'")
    assert remaining == 1
    orphan = await pool.fetchval(
        "SELECT count(*) FROM policy_embeddings WHERE source_file = 'a.md' AND chunk_index = 1"
    )
    assert orphan == 0
