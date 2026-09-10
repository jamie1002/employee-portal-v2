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

### Requirement: 檢索門檻與落空處理

系統 SHALL 以餘弦相似度對 `policy_embeddings` 排序，並僅保留分數大於等於
`RETRIEVAL_MIN_SCORE` 的結果；當保留結果為空時，系統 SHALL 改用一個受限的
fallback 提示呼叫生成模型，該提示 MUST NOT 產生任何具體的公司規定、時間、天數、
金額或計算方式，僅得用於寒暄、同理與引導。

#### Scenario: 分數高於門檻的結果被保留
- **GIVEN** 某 chunk 與查詢向量的餘弦相似度為 0.70，`RETRIEVAL_MIN_SCORE` 為 0.65
- **WHEN** 執行檢索
- **THEN** 該 chunk SHALL 出現在檢索結果中

#### Scenario: 分數等於門檻為邊界，SHALL 保留
- **GIVEN** 某 chunk 與查詢向量的餘弦相似度精確等於 `RETRIEVAL_MIN_SCORE`
- **WHEN** 執行檢索
- **THEN** 該 chunk SHALL 出現在檢索結果中（門檻為「大於等於」，不是「大於」）

#### Scenario: 全部結果被門檻篩掉時改走受限的 fallback 提示
- **GIVEN** 查詢與語料庫中所有 chunk 的相似度皆低於 `RETRIEVAL_MIN_SCORE`
  （例如使用者輸入「早安」或抱怨工作壓力）
- **WHEN** 呼叫 `chat.ask()`
- **THEN** 系統 SHALL 以 fallback 提示呼叫生成模型並回傳 `kind: "fallback"`、
  `refused: true`、`sources: []`，且 MUST NOT 使用政策問答的系統提示
  （沒有檢索依據時使用該提示會讓模型憑空談論規定）

#### Scenario: 打招呼與情緒性輸入得到自然回應
- **GIVEN** 使用者輸入「早安」、「你好」這類問候，或帶有情緒的抱怨
- **WHEN** 呼叫 `POST /api/chat`
- **THEN** 系統 SHALL 回應親切的問候或同理，並引導至可以協助的方向
  （政策問題範例、或建議聯繫人資與主管），MUST NOT 回覆制式的「查無相關規定」

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

### Requirement: 生成硬約束與推算界線

系統 SHALL 要求生成模型僅依據「檢索到的片段」與「系統當前生效的考勤設定」回答；
模型 MAY 將這些資料中明確記載的規則與數值套用到使用者提供的情境上進行推算
（比較、單位換算、級距對照），但 MUST NOT 憑空發明資料中沒有的規則或數值。
凡屬推算而得的答案，回答 MUST 附上「以系統實際顯示為準」意涵的提醒。

> 第一版一律禁止推算，導致語料明確寫著「09:11:00 才算遲到」時，模型仍無法回答
> 「9:20 打卡算不算遲到」。RAG 語料無法窮舉所有數值案例，禁止規則套用等同讓助理
> 退化成文件複讀機，因此改為依「推算依據是否來自提供的資料」分界。

#### Scenario: 依據明確時推算並直接回答
- **GIVEN** 檢索片段記載「打卡時間超過應到班時間加緩衝即為遲到，09:11:00 才算遲到」
- **WHEN** 使用者詢問「我 9:20 打卡算遲到嗎」
- **THEN** 系統 SHALL 直接回答會判定為遲到，並附上「以系統實際顯示為準」的提醒，
  MUST NOT 以「文件未直接列出」為由拒答

#### Scenario: 依據不在資料中時不得發明
- **GIVEN** 檢索片段完全沒有記載加班費的計算方式
- **WHEN** 使用者詢問「加班費一小時多少錢」
- **THEN** 系統 SHALL 說明文件未涵蓋此主題，MUST NOT 自行套用任何公式或金額

#### Scenario: 前提不明確時給出條件式回答
- **GIVEN** 使用者的問題涉及模型無法得知的前提（例如當天是否有已核准的請假會使
  應到班時間後推、或請假區間跨越哪一週而不知有無國定假日）
- **WHEN** 生成回答
- **THEN** 回答 SHALL 依預設情況給出結論並明確標示該前提，MUST NOT 直接拒答，
  也 MUST NOT 假裝該前提不存在

#### Scenario: 有答案時附上來源
- **GIVEN** 檢索到的片段可回答使用者的問題
- **WHEN** 生成回答
- **THEN** 回答文字 SHALL 包含依據片段的 `source_file` 與 `section_path`
  （供 eval 自動驗證答案有所本；前端一律剝除不顯示給使用者）

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
