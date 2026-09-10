"""檢索：排序、門檻過濾（含邊界）、top_k 上限（SPEC.md §4.12 Requirement 3）。

分數的邊界測試刻意不寫死一個猜測出來的門檻值——pgvector 的 `vector` 型別是單精度
浮點數，猜一個「理論上等於某個門檻」的值容易被儲存時的浮點捨入誤差打臉。做法是先以
`min_score=-1`（不過濾）量出資料庫實際回傳的分數，再把該分數原封不動設成
`RETRIEVAL_MIN_SCORE`，這樣「等於門檻」的比較用的是同一個浮點數，不受精度影響。
"""

from app.config.settings import app_settings
from app.repositories import policy_repository
from app.services import policy_retrieval
from tests.helpers_chat import FakeGeminiClient, clean_policy_embeddings, make_unit_vector

__all__ = ["clean_policy_embeddings"]


async def test_results_sorted_by_similarity_descending(pool, monkeypatch, clean_policy_embeddings):
    monkeypatch.setattr(app_settings, "RETRIEVAL_MIN_SCORE", -1.0)
    query_vector = make_unit_vector([1.0])
    # 與 query 的相似度依序遞減：high > mid > low
    await policy_repository.upsert_chunk(
        pool, "s.md", 0, "測試 > 高", "高", "高", "h0", make_unit_vector([1.0, 0.1])
    )
    await policy_repository.upsert_chunk(
        pool, "s.md", 1, "測試 > 中", "中", "中", "h1", make_unit_vector([1.0, 1.0])
    )
    await policy_repository.upsert_chunk(
        pool, "s.md", 2, "測試 > 低", "低", "低", "h2", make_unit_vector([0.0, 1.0])
    )

    client = FakeGeminiClient(query_vector=query_vector)
    results = await policy_retrieval.retrieve(pool, client, "任意問題")

    assert [r.section_path for r in results] == ["測試 > 高", "測試 > 中", "測試 > 低"]
    assert results[0].score > results[1].score > results[2].score


async def test_score_equal_to_threshold_is_kept(pool, monkeypatch, clean_policy_embeddings):
    monkeypatch.setattr(app_settings, "RETRIEVAL_MIN_SCORE", -1.0)
    query_vector = make_unit_vector([1.0])
    await policy_repository.upsert_chunk(
        pool, "b.md", 0, "測試 > 邊界", "內容", "內容", "hash0", make_unit_vector([3.0, 4.0])
    )
    client = FakeGeminiClient(query_vector=query_vector)

    unfiltered = await policy_retrieval.retrieve(pool, client, "任意問題")
    exact_score = unfiltered[0].score

    monkeypatch.setattr(app_settings, "RETRIEVAL_MIN_SCORE", exact_score)
    kept = await policy_retrieval.retrieve(pool, client, "任意問題")

    assert len(kept) == 1
    assert kept[0].score == exact_score


async def test_score_below_threshold_is_dropped(pool, monkeypatch, clean_policy_embeddings):
    monkeypatch.setattr(app_settings, "RETRIEVAL_MIN_SCORE", -1.0)
    query_vector = make_unit_vector([1.0])
    await policy_repository.upsert_chunk(
        pool, "b.md", 0, "測試 > 邊界", "內容", "內容", "hash0", make_unit_vector([3.0, 4.0])
    )
    client = FakeGeminiClient(query_vector=query_vector)
    unfiltered = await policy_retrieval.retrieve(pool, client, "任意問題")
    exact_score = unfiltered[0].score

    monkeypatch.setattr(app_settings, "RETRIEVAL_MIN_SCORE", exact_score + 0.0001)
    dropped = await policy_retrieval.retrieve(pool, client, "任意問題")

    assert dropped == []


async def test_top_k_limit_is_enforced(pool, monkeypatch, clean_policy_embeddings):
    monkeypatch.setattr(app_settings, "RETRIEVAL_MIN_SCORE", -1.0)
    monkeypatch.setattr(app_settings, "RETRIEVAL_TOP_K", 2)
    query_vector = make_unit_vector([1.0])
    for i in range(4):
        await policy_repository.upsert_chunk(
            pool, "k.md", i, f"測試 > {i}", f"內容{i}", f"內容{i}", f"hash{i}", make_unit_vector([1.0, float(i)])
        )
    client = FakeGeminiClient(query_vector=query_vector)

    results = await policy_retrieval.retrieve(pool, client, "任意問題")

    assert len(results) == 2
