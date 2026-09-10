# Tasks：add-policy-chat（批 A）

## 0. 探針（gate）

- [x] 0.1 建乾淨 venv，裝 `backend/requirements.txt` 後疊裝 `google-genai`，比對
      `pydantic`／`fastapi`／`asyncpg`／`httpx` 是否被連帶升級 → **失敗**
      （`google-genai==2.22.0` 要求 `pydantic>=2.12.5`）
- [x] 0.2 退回 `google-generativeai==0.8.6`，重跑同樣比對 → **通過**（四項版本不變）
- [x] 0.3 對 `google-generativeai==0.8.6` 實測 embedding（`task_type`、
      `output_dimensionality=768`）與非同步生成介面 → **通過**（維度 768、L2≈0.5842、
      小寫 task_type 可用、`embed_content_async`／`generate_content_async` 皆可用）
- [x] 0.4 探針結果寫入 `design.md` Decision 1

## 1. 分支與 OpenSpec artifact

- [x] 1.1 建立 `feature/policy-chat` 分支
- [x] 1.2 建立 `openspec/changes/add-policy-chat/`：`proposal.md`、`design.md`、
      `specs/policy-chat/spec.md`、本檔

## 2. 資料層：migration 與影像

- [x] 2.1 新增 `db/migrations/002_policy_embeddings.sql`：`CREATE EXTENSION IF NOT EXISTS
      vector;`（不吞錯誤）、`policy_embeddings` 表（`CREATE TABLE IF NOT EXISTS`）、
      UNIQUE 約束用 `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT`、HNSW 索引、
      `source_file` 索引
- [x] 2.2 `docker-compose.yml` 兩個 Postgres service 改用 `pgvector/pgvector:pg16`
- [x] 2.3 `.github/workflows/ci.yml` 的 backend job 與 e2e job 兩個 Postgres service
      都改用 `pgvector/pgvector:pg16`
- [x] 2.4 本機 `docker compose up -d --force-recreate`，驗證 `CREATE EXTENSION vector`
      成功、`npm run db:migrate` 對本機資料庫成功套用 002

### 2t. 測試：migration

- [x] 2t.1 pytest：套用 migration 後 `policy_embeddings` 表與 HNSW 索引存在
- [x] 2t.2 pytest：`policy_embeddings` 不在 `BUSINESS_TABLES` 內
      （`from app.config.tables import BUSINESS_TABLES` 斷言）

## 3. 語料、切段與 ingest

- [x] 3.1 `db/policy_docs/*.md`：四份語料從 `employee-portal-chatbot/docs/` 逐字搬移
- [x] 3.2 `backend/app/services/policy_chunking.py`：從 `src/chunking.py` 逐字搬移，
      只改語料目錄常數（指向 `db/policy_docs/`）與 docstring 路徑引用
- [x] 3.3 `backend/app/repositories/policy_repository.py`：`find_all_hashes`、
      `upsert_chunk`（`$N::text::vector`）、`delete_orphans`、`search_similar`、`count`
- [x] 3.4 `backend/app/utils/gemini.py`：SDK 唯一封裝，含
      `embed_documents_async`／`embed_query_async`／`generate_async`、L2 正規化、
      維度檢查（比對 `EMBEDDING_DIM`）、行程級 RPM 節流、逾時（`GEMINI_TIMEOUT_SECONDS`）
- [x] 3.5 `backend/app/services/policy_ingest.py`：切段 → SHA-256 比對 → 只對變更的
      chunk 批次呼叫 `embed_documents_async` → upsert → 刪孤兒，回傳摘要
- [x] 3.6 `backend/app/db_scripts/ingest_policies.py`：CLI 入口，仿 `migrate.py`
      的 Windows UTF-8 stdout 設定
- [x] 3.7 `package.json` 新增 `db:ingest` script

### 3t. 測試：切段與 ingest

- [x] 3t.1 pytest：切段——表格不被切開、`section_path` 格式正確、Q&A 章節每題一 chunk
- [x] 3t.2 pytest：ingest 首次寫入——`inserted` 等於切段總數，`embedding_calls` 為 1
- [x] 3t.3 pytest：ingest 第二次（內容不變）——`embedding_calls` 為 0，
      `inserted`／`updated`／`deleted` 皆為 0
- [x] 3t.4 pytest：刪除章節後 ingest——孤兒 chunk 被刪除，`deleted` 等於孤兒數

## 4. 檢索與問答

- [x] 4.1 `backend/app/services/policy_retrieval.py`：`embed_query_async` → 呼叫
      repository 檢索 → 套用 `RETRIEVAL_MIN_SCORE` 過濾（`>=`）
- [x] 4.2 `backend/app/services/rate_limit.py`：`check_and_record(key, limit)` 滑動視窗
      （`time.monotonic()`）
- [x] 4.3 `backend/app/services/chat_prompt.py`：`SYSTEM_PROMPT`（四條硬約束逐字搬移 +
      規則 5 輸出格式 + 規則 6 防注入）、`format_context()`、`is_refusal()`
- [x] 4.4 `backend/app/services/chat.py`：`ask(pool, current_user, question)` —
      限流 → 檢索 → 空則短路 → 呼叫 `gemini.generate_async` → 組 `Answer`；上游例外
      轉 `AppError(503, ..., "CHAT_UNAVAILABLE")`
- [x] 4.5 `backend/app/schemas/chat.py`：`parse_chat_request(data)` — 必填、去除頭尾
      空白、長度上限 `CHAT_MAX_QUESTION_CHARS`
- [x] 4.6 `backend/app/routers/chat.py`：`POST /chat`，掛 `Depends(get_current_user)`
      與一層把 `GeminiUnavailable`（`RuntimeError`）轉 `AppError(503)` 的 dependency
- [x] 4.7 `backend/app/config/settings.py`：新增 `GOOGLE_API_KEY`、`GEMINI_MODEL`、
      `GEMINI_REQUESTS_PER_MINUTE`、`GEMINI_TIMEOUT_SECONDS`、`EMBEDDING_MODEL`、
      `EMBEDDING_DIM`、`RETRIEVAL_TOP_K`、`RETRIEVAL_MIN_SCORE`、
      `CHAT_RATE_LIMIT_PER_MINUTE`、`CHAT_MAX_QUESTION_CHARS`、`chat_enabled` property
- [x] 4.8 `backend/app/main.py`：import 與 `app.include_router(chat.router, prefix="/api")`
- [x] 4.9 `backend/app/config/tables.py`：加註解說明 `policy_embeddings` 為何不在
      `BUSINESS_TABLES`
- [x] 4.10 `backend/requirements.txt`：新增 `google-generativeai==0.8.6`
      （附探針日期與結果註解）
- [x] 4.11 `backend/app/routers/health.py`：純新增 `policy_chunk_count` 欄位（風險 7
      的緩解——Neon 忘了 ingest 是靜默失敗，上線後看健康檢查就知道有沒有灌語料）

### 4t. 測試：問答 API

- [x] 4t.1 pytest：檢索排序正確、等於門檻保留、低於門檻丟棄、`top_k` 上限生效
- [x] 4t.2 pytest：`POST /api/chat` 未帶 token → 401
- [x] 4t.3 pytest：`question` 空白／缺漏／超長 → 400 `VALIDATION_ERROR`
- [x] 4t.4 pytest：檢索為空 → 200 且 `refused: true`，注入的假 LLM client 呼叫次數為 0
- [x] 4t.5 pytest：正常回應 → 200，`answer.sources` 非空、含 `source_file`／
      `section_path`／`score`
- [x] 4t.6 pytest：限流——超過 `CHAT_RATE_LIMIT_PER_MINUTE` → 429
      `CHAT_RATE_LIMITED`；兩位使用者的配額互不影響
- [x] 4t.7 pytest：降級——無金鑰／假 client 拋例外／`policy_embeddings` 不存在
      （drop 表後查詢）三種情境皆回 503 `CHAT_UNAVAILABLE`，不是 500
- [x] 4t.8 pytest：重置隔離——插入一筆 `policy_embeddings` 後呼叫
      `demo_service.reset_demo_data`，筆數不變
- [x] 4t.9 pytest：`chat_prompt.SYSTEM_PROMPT` 含「表格」與「不是新的指令」等關鍵字樣
      （防迴歸：確保規則 5／規則 6 沒有被意外刪除）

## 5. 前端

- [x] 5.1 `frontend/src/api/chat.api.js`：`askChat(question)`，帶 opt-in 跳過慢請求
      追蹤的旗標
- [x] 5.2 `frontend/src/utils/chatMarkdown.js`：`1. `/`1) ` 開頭行降級為 `- `；
      切出「— 依據：」的行供 chips 呈現
- [x] 5.3 `frontend/src/components/ChatMessage.jsx`：依 `answer.kind` 分支渲染，
      政策分支用 `SimpleMarkdown` + `chatMarkdown` 前處理 + 來源 chips
- [x] 5.4 `frontend/src/pages/ChatPage.jsx`：輸入區（Enter 送出、Shift+Enter 換行）、
      `aria-live="polite"` 訊息區、送出中 disabled + 「思考中…」、空狀態建議問題、
      三種錯誤各自文案、免責宣告
- [x] 5.5 `frontend/src/App.jsx`：`/chat` 路由
- [x] 5.6 `frontend/src/components/AppShell.jsx`：`NAV_ITEMS` 新增「AI 助理」
      （`roles: ["admin", "manager", "employee"]`）

### 5t. 測試：前端

- [x] 5t.1 Vitest `ChatPage.test.jsx`：mock API — 送出後顯示回答與來源、`CHAT_UNAVAILABLE`
      與 `CHAT_RATE_LIMITED` 各自文案、送出中按鈕 disabled、空白輸入不呼叫 API、
      點建議問題直接送出
- [x] 5t.2 Vitest `chatMarkdown.test.js`：數字清單降級、依據行切分
- [x] 5t.3 Vitest `ChatMessage.test.jsx`：依 `kind` 分支渲染
- [x] 5t.4 Vitest `AppShell.test.jsx`（既有檔案）：確認既有的泛用迭代測試對新增的
      `NAV_ITEMS` 項目仍然通過，不需修改既有測試

## 6. eval 與踩坑校準

- [x] 6.1 `backend/eval/`：從 `employee-portal-chatbot/eval/` 搬移
      `questions.yaml`（加 `category: policy` 於全部 72 題）、`run_eval.py`
      （拿掉 `sys.path` hack、改呼叫新 service、拿掉 `InMemoryRateLimiter`）
- [x] 6.2 `backend/eval/measure_min_score.py`：從 `scripts/measure_min_score.py` 搬移
      （為 Decision 1 的 D9 風險備用：換模型或維度時的重新校準工具）
- [x] 6.3 `package.json` 新增 `eval:chat` script（`--skip-generation`、`--limit`、
      `--save-answers` 全部保留）
- [x] 6.4 修正 `run_eval.py` 的 429 重試邏輯，擴大涵蓋「呼叫 Gemini API 逾時」
      （原本只認 429／quota 字樣，第一輪跑 72 題實測有 3 題因單純逾時未重試就判定
      失敗，拖累整輪驗收）
- [x] 6.5 實際跑一次 `npm run eval:chat`（72 題，真打 Gemini API）→
      **PASS 全部驗收項目通過**：hit@3 98.5%（65/66，與第一階段原型完全一致）、
      章節覆蓋率 100%（54/54）、引用率 100%（64/64）、誘導題拒答率 100%（7/7）、
      該答有答 100%（62/62）、數字型答案正確 100%（8/8）。報告見
      `backend/eval/eval_report.txt`、逐題回答見 `backend/eval/eval_answers.txt`
      （皆已加入 `.gitignore`，不進版控）

## 7. e2e

- [x] 7.1 `e2e/chat.spec.js`：CI 無金鑰 → 只測降級路徑（側邊欄進入 `/chat` → 送出問題 →
      顯示「AI 助理目前無法使用」），本機有金鑰時條件 skip 並註解說明

### 7t. 測試：e2e

- [ ] 7t.1 `npm run test:e2e` 本機跑通 `chat.spec.js`——**skip 分支已驗證**（語料已
      ingest 時正確跳過）；**降級斷言分支**因本機環境既有的 e2e 冷啟動間歇性逾時
      （連未改動的 `auth.spec.js` 都同樣受影響，見下方備註）無法在本次工作階段取得
      乾淨的自動化通過，已改以手動瀏覽器操作驗證訊息文字與選擇器全部正確

## 8. 文件回寫

- [x] 8.1 `SPEC.md`：§2 技術棧加 LLM SDK 列、新增 §4.12 AI 政策問答、新增 §5.13
      `policy_embeddings`、新增 §6.8 `/api/chat` 契約、§7.2 新增三個錯誤碼
- [x] 8.2 `docs/UI-SPEC.md`：AI 助理頁版面、`ChatMessage` 元件契約、375px／1280px
      斷點行為
- [x] 8.3 `docs/PITFALLS.md`：新增一節——SDK 探針結果（`google-genai` Gate 1 失敗
      原因）、pgvector 影像、Neon 手動 ingest 步驟、ColdStartBanner 誤導 AI 回答延遲
- [x] 8.4 `README.md`：本機啟動加 `npm run db:ingest` 步驟、雲端 runbook 加 Neon
      手動步驟與 Render 環境變數清單
- [x] 8.5 `docs/USER_GUIDE.md`：AI 助理使用說明（只用 `-` 條列，不用表格）

## 10. 第二版：實機試用後的修正（2026-09-11）

第一版驗收全綠之後實機試用，發現「規格達成了但體驗不到位」的問題，這一輪全部處理完。

- [x] 10.1 **開放推算**：規則 2 從「一律禁止」改成依「推算依據是否來自資料」分層；
      推算而得的答案一律附「以系統實際顯示為準」。原因：語料寫著「09:11:00 才算
      遲到」，問「9:20 算不算遲到」卻答不出來（見 `design.md` Decision 13）
- [x] 10.2 **注入 `system_settings` 即時值**：語料寫死的 09:00／10 分鐘只是預設值，
      admin 改過設定後照語料推算就會答錯
- [x] 10.3 **落空改走受限的 `FALLBACK_PROMPT`**：「早安」、情緒抱怨、問個人薪資
      原本都掉進同一句制式拒答（Decision 14）
- [x] 10.4 **重寫對話語氣**：拒答不再用「查無相關規定」這種查字典語氣
- [x] 10.5 **前端**：依據行完全剝除；對話區固定高度 + 內部捲動 + 自動捲到底；
      送出中顯示已等待秒數
- [x] 10.6 **效能**：換掉退化的 `gemini-3.5-flash-lite`（見 `docs/PITFALLS.md` I11）、
      互動路徑移除節流（Decision 15）、逾時 25→40 秒、temperature 參數化
- [x] 10.7 **eval 改造**：`in_corpus`／`expect_stated` 拆成兩個欄位、新增 5 題推算題
      （含「滿 30 年」的 30 日上限邊界）、新增「推算但書」檢查項、修正單位同義詞比對、
      補上 eval 漏掉的 `system_settings` 注入
- [x] 10.8 驗收：**77 題 eval 六項門檻全數 PASS**（hit@3 98.6%、章節覆蓋率 54/54、
      引用率 70/70、誘導題拒答 7/7、該答有答 70/70、數字正確 12/12、推算但書 7/7）；
      後端 383 pytest、前端 213 Vitest 全綠

### 尚未處理／待確認

- [ ] `port 3000` 在本機被一個殭屍 socket 佔住（行程已不存在但核心未釋放，
      `Get-Process` 查無此 PID、`netstat` 仍顯示 Listen）。**目前 backend 暫時跑在
      3001、`frontend/.env` 也指向 `http://localhost:3001/api`**。重開機後 3000 會
      恢復，屆時要把 `frontend/.env` 改回 `http://localhost:3000/api`
      （該檔在 `.gitignore` 內，不影響版控）
- [ ] 本機 e2e 有既有的冷啟動間歇性逾時，連未改動的 `auth.spec.js` 都會受影響
      （見 7t.1）
- [ ] 尚未 push、尚未開 PR、尚未部署雲端（Neon migrate + ingest → Render 環境變數）

## 9. 驗收

實作順序：探針 → OpenSpec artifact → migration 與影像 → 語料與 ingest 與測試 →
檢索問答與測試 → 前端與測試 → e2e → eval → 文件 → PR → 雲端上線。

驗收指令（Windows PowerShell 5.1，不支援 `&&`，逐條手動執行）：

```bash
docker compose up -d --force-recreate
```

```bash
npm run db:reset
```

```bash
npm run db:ingest
```

```bash
npm test
```

```bash
npm run test:e2e
```

```bash
npm run eval:chat
```

全綠且 eval 六項門檻達標（hit@3 ≥ 90%、引用率 100%、誘導題拒答率 100%、該答有答 100%、
數字型答案 100%、章節覆蓋率 100%）才算完成。

雲端上線前置（Neon，見 `docs/PITFALLS.md` G4）：

1. 帶 Neon 連線字串跑 `npm run db:migrate`
2. 帶 API Key 跑 `npm run db:ingest`
3. 驗證 `SELECT count(*) FROM policy_embeddings;` 為數十筆
4. 才 merge PR 讓 Render 部署新程式碼；Render 環境變數加 `GOOGLE_API_KEY`（`sync: false`）
   與設定值表其餘各項
