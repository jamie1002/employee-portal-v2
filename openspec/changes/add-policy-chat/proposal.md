# 提案：AI 政策問答助理（批 A）

## Why

`employee-portal-v2` 是作品集展示用的員工入口網站，目前所有頁面都是傳統表單與清單，
沒有任何能展示「與 AI 整合」能力的功能。獨立原型專案 `employee-portal-chatbot` 已完成
第一階段：四份公司政策文件（考勤規則、請假辦法、產品目錄、公司簡介）切成 61 個 chunk、
建立 72 題黃金題庫，兩軌驗收全綠（hit@3 98.5%、引用率／誘導題拒答率／該答有答／數字型
答案皆 100%）。批 8 已把 embedding 從本機 `BAAI/bge-m3` 遷移到 Gemini API 的 768 維，
目的就是讓這個功能能塞進 `render.yaml` 的 Render 免費方案（記憶體上限 512MB，本機模型
跑不起來）。

這個 change 把該原型整合進 `employee-portal-v2`，讓面試官能直接在線上的員工入口網站裡
點開「AI 助理」實際提問，而不必另外開一個獨立的 demo。

範圍**只包含政策文件問答**（完全唯讀、不碰任何個人資料），對應 `SPEC.md` 即將新增的
§4.12／§5.13／§6.8。個人出勤／假別／申請進度的查詢工具（授權邊界完全不同的風險等級）
留給批 B，本 change 刻意不做，但在「為批 B 鋪路」一節記錄了為它預留的擴充點。

## 技術決策摘要（不重新討論，理由見 `design.md`）

- LLM SDK：**探針結果 `google-genai` 未通過 Gate 1**（見 design.md Decision 1），
  實際採用 `google-generativeai==0.8.6`。
- 不帶 LangChain：v2 只需要「一次 prompt、一次呼叫」，LCEL 的價值為零。
- 走 OpenSpec：v2 重建批 0～9 已全部完成，這是第一個適用的 change。
- 改動紀律：**只能增加，不得更動既有邏輯與 UI/UX 規則**。所有修改既有檔案的動作都必須是
  純新增（新欄位、新路由行、新選單項、新 script）。

## Capabilities

### New Capabilities

- `policy-chat`：政策文件問答（唯讀 RAG，見 `specs/policy-chat/spec.md`）

## What Changes

### 後端（新增）

- `db/migrations/002_policy_embeddings.sql`：`policy_embeddings` 表 + pgvector HNSW 索引。
- `db/policy_docs/*.md`：四份語料逐字搬移。
- `backend/app/utils/gemini.py`：Gemini SDK 的唯一封裝（L2 正規化、維度檢查、節流、逾時）。
- `backend/app/repositories/policy_repository.py`：`policy_embeddings` 的全部 SQL。
- `backend/app/services/policy_chunking.py`：切段純函式，從原型逐字搬移。
- `backend/app/services/policy_ingest.py`：切段 → hash 比對 → 增量 embedding → upsert → 刪孤兒。
- `backend/app/services/policy_retrieval.py`：embed query → 檢索 → `min_score` 過濾。
- `backend/app/services/chat_prompt.py`：系統提示、context 組裝、拒答偵測（純字串函式）。
- `backend/app/services/chat.py`：限流 → 檢索 → 空則短路 → 生成 → 組回應。
- `backend/app/services/rate_limit.py`：通用滑動視窗限流。
- `backend/app/schemas/chat.py`：`parse_chat_request`（手刻驗證）。
- `backend/app/routers/chat.py`：`POST /api/chat`。
- `backend/app/db_scripts/ingest_policies.py`：ingest CLI 入口。
- `backend/eval/`：72 題黃金題庫、評估腳本、門檻校準腳本（從原型搬移）。

### 後端（純新增修改）

- `backend/app/config/settings.py`：新增 11 個環境變數欄位與 `chat_enabled` property。
- `backend/app/main.py`：掛載 chat router。
- `backend/app/config/tables.py`：只加註解，不動 `BUSINESS_TABLES` 清單本身。
- `backend/requirements.txt`：新增 `google-generativeai==0.8.6`（附探針日期與結果的註解）。
- `docker-compose.yml`：兩個 Postgres service 改用 `pgvector/pgvector:pg16`。
- `.github/workflows/ci.yml`：backend job 與 e2e job 的 Postgres service 都改用 pgvector 影像。
- `render.yaml`、`.env.example`、`package.json`：新增環境變數與 `db:ingest` / `eval:chat` script。

### 前端（新增）

- `frontend/src/api/chat.api.js`、`pages/ChatPage.jsx`、`components/ChatMessage.jsx`、
  `utils/chatMarkdown.js`，各自的同名測試檔。

### 前端（純新增修改）

- `frontend/src/App.jsx`：`/chat` 路由。
- `frontend/src/components/AppShell.jsx`：`NAV_ITEMS` 新增一筆「AI 助理」。

### 文件（依 CLAUDE.md 規則，重大新增必須同步更新規格）

- `SPEC.md`：§2 技術棧、新增 §4.12／§5.13／§6.8、§7.2 三個新錯誤碼。
- `docs/UI-SPEC.md`：AI 助理頁版面、元件契約、斷點行為。
- `docs/PITFALLS.md`：新增一節記錄 SDK 探針結果、pgvector 影像、Neon 手動 ingest、
  ColdStartBanner 誤導。
- `README.md`：本機啟動加 ingest 步驟、雲端 runbook 加 Neon 步驟與 Render 環境變數。
- `docs/USER_GUIDE.md`：AI 助理使用說明。

## Impact

- **受影響的 capability**：新增 `policy-chat`，不修改任何既有 capability 的行為。
- **受影響的既有檔案**（全部純新增，見上）：`settings.py`、`main.py`、`tables.py`、
  `requirements.txt`、`docker-compose.yml`、`.github/workflows/ci.yml`、`render.yaml`、
  `.env.example`、`package.json`、`App.jsx`、`AppShell.jsx`。
- **不受影響**：`DashboardPage.jsx`（刻意不加快捷卡片，避免改動既有首頁版面）、
  `SimpleMarkdown.jsx`（刻意不擴充渲染器，見 design.md Decision 7）。
- **部署面**：Neon 正式資料庫需要先手動跑 migration + ingest 才能 merge PR（見
  `docs/PITFALLS.md` G4：push 不會自動更新雲端資料庫）。Render 需新增
  `GOOGLE_API_KEY`（`sync: false`）等環境變數。
