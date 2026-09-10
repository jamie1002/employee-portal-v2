"""migration 002：policy_embeddings 表、HNSW 索引、以及不進 BUSINESS_TABLES（SPEC.md §5.13）。"""

from app.config.tables import BUSINESS_TABLES


async def test_policy_embeddings_table_and_index_exist(db):
    table_exists = await db.fetchval(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'policy_embeddings'"
    )
    assert table_exists == 1

    index_exists = await db.fetchval(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'idx_policy_embeddings_hnsw'"
    )
    assert index_exists == 1


def test_policy_embeddings_not_in_business_tables():
    assert "policy_embeddings" not in BUSINESS_TABLES
