## ADDED Requirements

### Requirement: 政策語料向量化儲存

系統 SHALL 將 `db/policy_docs/*.md` 的內容切段後計算 embedding 並儲存於
`policy_embeddings` 表，且 SHALL 以 `raw_content` 的 SHA-256 雜湊判斷內容是否變更，
未變更的 chunk 不得重新呼叫 embedding API。

#### Scenario: 首次寫入空表
- **GIVEN** `policy_embeddings` 表為空
- **WHEN** 執行 ingest
- **THEN** 系統 SHALL 為每一個切段結果呼叫一次批次 embedding API，並將結果全部寫入 `policy_embeddings`

#### Scenario: 內容未變更時不重打 API
- **GIVEN** `policy_embeddings` 表已包含上一次 ingest 的完整結果
- **WHEN** 語料內容未變更，再次執行 ingest
- **THEN** 系統 SHALL 比對每個 chunk 的 `content_hash`，全部相符時 SHALL 不呼叫 embedding API（呼叫次數為 0）

#### Scenario: 刪除章節後孤兒 chunk 被刪除
- **GIVEN** `policy_embeddings` 已有來源檔 `X` 的 chunk
- **WHEN** 語料中刪除了該章節後重新執行 ingest
- **THEN** 系統 SHALL 刪除資料庫中已不存在於本次切段結果的 `(source_file, chunk_index)` 列

### Requirement: 向量表不受展示資料重置影響

`policy_embeddings` 表 SHALL NOT 被列入 `BUSINESS_TABLES`，展示資料的種子重新載入與
閒置自動重置 MUST NOT 清空此表。

#### Scenario: 閒置自動重置不影響語料
- **GIVEN** `policy_embeddings` 已有已 ingest 的資料，筆數為 N
- **WHEN** 系統觸發展示資料閒置自動重置（`demo_auto_reset`）
- **THEN** 重置完成後 `policy_embeddings` 的筆數 SHALL 仍為 N

### Requirement: 檢索門檻與短路

系統 SHALL 以餘弦相似度對 `policy_embeddings` 排序，並僅保留分數大於等於
`RETRIEVAL_MIN_SCORE` 的結果；當保留結果為空時，系統 SHALL 短路直接回傳拒答，
MUST NOT 呼叫生成模型。

#### Scenario: 分數高於門檻的結果被保留
- **GIVEN** 某 chunk 與查詢向量的餘弦相似度為 0.70，`RETRIEVAL_MIN_SCORE` 為 0.65
- **WHEN** 執行檢索
- **THEN** 該 chunk SHALL 出現在檢索結果中

#### Scenario: 分數等於門檻為邊界，SHALL 保留
- **GIVEN** 某 chunk 與查詢向量的餘弦相似度精確等於 `RETRIEVAL_MIN_SCORE`
- **WHEN** 執行檢索
- **THEN** 該 chunk SHALL 出現在檢索結果中（門檻為「大於等於」，不是「大於」）

#### Scenario: 全部結果被門檻篩掉時不呼叫生成模型
- **GIVEN** 查詢與語料庫中所有 chunk 的相似度皆低於 `RETRIEVAL_MIN_SCORE`
- **WHEN** 呼叫 `chat.ask()`
- **THEN** 系統 SHALL 回傳 `refused: true` 且 `text` 為固定拒答文字，MUST NOT 呼叫 Gemini 生成 API

### Requirement: `POST /api/chat` 契約

系統 SHALL 提供 `POST /api/chat` 端點，接受已登入使用者的問題並回傳結構化答案。

#### Scenario: 成功回應（200）
- **GIVEN** 使用者已登入並帶有效 Bearer token，問題非空白且未超過字數上限
- **WHEN** 呼叫 `POST /api/chat`，body 為 `{"question": "..."}`
- **THEN** 系統 SHALL 回應 200，body 為 `{"answer": {"kind": "policy", "text", "refused", "sources": [...]}}`

#### Scenario: 缺少或無效問題（400）
- **GIVEN** 使用者已登入
- **WHEN** `question` 欄位缺漏、為空白字串、或超過 `CHAT_MAX_QUESTION_CHARS`
- **THEN** 系統 SHALL 回應 400，`error.code` 為 `VALIDATION_ERROR`

#### Scenario: 未登入（401）
- **GIVEN** 請求未帶 Authorization header 或 token 無效／逾期
- **WHEN** 呼叫 `POST /api/chat`
- **THEN** 系統 SHALL 回應 401，`error.code` 為 `UNAUTHORIZED` 或 `INVALID_TOKEN`

### Requirement: 生成硬約束

系統 SHALL 要求生成模型僅依據檢索到的片段回答問題：有答案時 MUST 附上來源章節路徑，
片段中查無對應內容時 MUST 拒答，不得憑既有知識推測或補充。

#### Scenario: 有答案時附上來源
- **GIVEN** 檢索到的片段可直接回答使用者的問題
- **WHEN** 生成回答
- **THEN** 回答文字 SHALL 包含依據片段的 `source_file` 與 `section_path`

#### Scenario: 片段無法直接回答時拒答
- **GIVEN** 檢索到的片段主題相關但未直接回答使用者的問題
- **WHEN** 生成回答
- **THEN** 回答 SHALL 標記為拒答（`refused: true`），MUST NOT 將片段內容套用到問題未涵蓋的情境上作為答案

### Requirement: 不可用時降級

當 Gemini 金鑰未設定、上游逾時或發生錯誤、或 `policy_embeddings` 表／`vector` extension
不存在時，系統 SHALL 回應 503 並帶明確錯誤碼，MUST NOT 回應未分類的 500。

#### Scenario: 未設定金鑰
- **GIVEN** `GOOGLE_API_KEY` 為空字串（`chat_enabled` 為否）
- **WHEN** 呼叫 `POST /api/chat`
- **THEN** 系統 SHALL 回應 503，`error.code` 為 `CHAT_UNAVAILABLE`

#### Scenario: 上游呼叫拋出例外
- **GIVEN** Gemini API 呼叫逾時或拋出非預期例外
- **WHEN** 呼叫 `POST /api/chat`
- **THEN** 系統 SHALL 攔截該例外並回應 503（`CHAT_UNAVAILABLE`），MUST NOT 讓例外以 500 外洩

### Requirement: 速率限制

系統 SHALL 對每位使用者的提問頻率做滑動視窗限流，超過 `CHAT_RATE_LIMIT_PER_MINUTE`
時 SHALL 回應 429；不同使用者的配額 MUST 互不影響。

#### Scenario: 超過限制
- **GIVEN** 使用者在一分鐘內已提問達到 `CHAT_RATE_LIMIT_PER_MINUTE` 次
- **WHEN** 該使用者再次呼叫 `POST /api/chat`
- **THEN** 系統 SHALL 回應 429，`error.code` 為 `CHAT_RATE_LIMITED`

#### Scenario: 不同使用者互不影響
- **GIVEN** 使用者 A 已達到提問頻率上限
- **WHEN** 使用者 B（未達上限）呼叫 `POST /api/chat`
- **THEN** 使用者 B 的請求 SHALL 正常處理，MUST NOT 被使用者 A 的限流狀態影響

### Requirement: AI 助理頁面

前端 SHALL 提供 `/chat` 路由頁面，允許 admin／manager／employee 三種角色存取，並在側邊欄
選單中顯示對應項目。

#### Scenario: 登入使用者可從選單進入
- **GIVEN** 使用者已登入（任一角色）
- **WHEN** 查看側邊欄選單
- **THEN** 選單 SHALL 顯示「AI 助理」項目，點擊後 SHALL 導向 `/chat`

#### Scenario: 手機寬度（375px）版面
- **GIVEN** 檢視埠寬度為 375px
- **WHEN** 開啟 `/chat` 頁面
- **THEN** 訊息輸入區與對話內容 SHALL 完整可見，MUST NOT 產生水平捲軸

#### Scenario: 桌機寬度（1280px）版面
- **GIVEN** 檢視埠寬度為 1280px
- **WHEN** 開啟 `/chat` 頁面
- **THEN** 頁面 SHALL 使用與其他既有頁面一致的版面寬度與側邊欄配置
