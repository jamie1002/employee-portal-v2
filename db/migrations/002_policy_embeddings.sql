-- ============================================================
-- 002_policy_embeddings.sql — AI 政策問答（批 A）向量索引
--
-- v2 沒有 schema_migrations 版本表，每次 migrate 會把所有 .sql 全部重跑
-- （docs/PITFALLS.md A4），本檔每一段都可重複執行。
--
-- CREATE EXTENSION 刻意不吞掉錯誤：本機／CI 的 Postgres 影像若忘了換成
-- pgvector/pgvector:pg16，這裡就會直接失敗，而不是等到 /api/chat 查詢時
-- 才安靜地壞掉（見 openspec/changes/add-policy-chat/design.md Decision 5）。
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_embeddings (
    id           SERIAL PRIMARY KEY,

    -- 來源追溯：回答時必須附上 source_file + section_path，使用者才能自己翻回原文查證。
    source_file  VARCHAR(100) NOT NULL,
    section_path TEXT         NOT NULL,   -- 例："請假辦法及福利制度 > 2. 假別與額度 > 2.1 特別休假級距"
    chunk_index  INTEGER      NOT NULL,   -- 同一份文件內的切段序號，從 0 起

    content      TEXT         NOT NULL,   -- 送進 LLM 的原文（已含 context prefix）
    raw_content  TEXT         NOT NULL,   -- 未加 prefix 的原始段落，供人工比對用

    -- 增量 ingest：內容雜湊沒變就跳過 embedding，省下重跑整份文件的時間。
    content_hash CHAR(64)     NOT NULL,

    -- gemini-embedding-001 原生 3072 維，這裡用 output_dimensionality 截斷成 768。
    -- 為什麼不用 3072：pgvector 的 HNSW 索引上限是 2000 維，3072 會建不起來。
    -- 換 embedding 模型或維度必須一併改這裡並重建整張表——維度不同的向量無法比較，
    -- 混在同一張表只會安靜地算出垃圾相似度（見 docs/PITFALLS.md 新增章節）。
    embedding    vector(768)  NOT NULL,

    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
    -- updated_at 用真實時間 now() 是維運事實不是業務時間戳，刻意不受虛擬時鐘規則約束，
    -- 也刻意不掛 set_updated_at 觸發器（既有觸發器與虛擬時鐘的矛盾見 docs/PITFALLS.md A3）。
);

ALTER TABLE policy_embeddings DROP CONSTRAINT IF EXISTS policy_embeddings_source_chunk_key;
ALTER TABLE policy_embeddings ADD CONSTRAINT policy_embeddings_source_chunk_key
    UNIQUE (source_file, chunk_index);

-- 餘弦距離索引。語料量小（數十個 chunk）時 HNSW 的效益不明顯，但先建好，
-- 避免語料變多才發現要改。
CREATE INDEX IF NOT EXISTS idx_policy_embeddings_hnsw
    ON policy_embeddings USING hnsw (embedding vector_cosine_ops);

-- 依來源檔篩選時用得到。
CREATE INDEX IF NOT EXISTS idx_policy_embeddings_source
    ON policy_embeddings (source_file);

-- 刻意不將 policy_embeddings 加進 app/config/tables.py 的 BUSINESS_TABLES：
-- 該清單會被種子載入 TRUNCATE，且正式環境有 15 分鐘閒置自動重置，加進去會讓
-- AI 助理每 15 分鐘失憶一次，且重建要重打數十次 embedding API（見
-- openspec/changes/add-policy-chat/design.md Decision 4）。
