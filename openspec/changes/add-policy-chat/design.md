# 設計：AI 政策問答助理（批 A）

## Context

`employee-portal-chatbot` 第一階段已完成獨立 RAG 原型並實證可用（72 題黃金題庫兩軌全綠）。
本 change 要把它整合進 `employee-portal-v2`，部署目標是 Render 免費方案（512MB 記憶體上限）
與 Neon.tech（PostgreSQL 16）。v2 的既有硬性規則（虛擬時鐘、deny-by-default 範圍限縮、
版本鎖定、禁止 mock 資料庫等）全部適用，本文件只記錄**因整合而新增的決策**。

## Decision 1：LLM SDK — 探針結果與最終選型

**原計畫**：採 Google 官方新 SDK `google-genai`，因為 LangChain 綁定的
`google-generativeai` 已被 Google 宣告停止維護，且 v2 只需要「一次 prompt、一次呼叫」，
LangChain LCEL 的價值為零。

**探針執行方式**：在暫存目錄建立乾淨 venv，先裝 v2 現有的 `backend/requirements.txt`
鎖定版本，再疊裝候選 SDK，比對疊裝前後 `pydantic`／`fastapi`／`asyncpg`／`httpx` 四項是否被
連帶升級。

**Gate 1 結果：`google-genai` 未通過**。

```
$ pip install -r backend/requirements.txt   # pydantic==2.10.4 鎖定
$ pip install google-genai                  # 疊裝
$ pip freeze | grep pydantic
pydantic==2.13.5    # 被連帶升級
```

原因是套件中繼資料明載 `Requires-Dist: pydantic<3.0.0,>=2.12.5`，這是 `google-genai==2.22.0`
的硬性下限，不是安裝順序或版本解析的偶然結果——只要疊裝這個套件版本，就一定會把 v2 鎖定的
`pydantic==2.10.4` 往上推。

**退回方案：`google-generativeai==0.8.6`（探針日期 2026-09-10）**。重跑 Gate 1，
`pydantic`／`fastapi`／`asyncpg`／`httpx` 四項全部原封不動地維持 v2 鎖定的版本。

**Gate 2／3 結果（對 `google-generativeai==0.8.6` 實測，打真實 Gemini API）**：

| 檢查項 | 結果 |
| :--- | :--- |
| `embed_content(task_type="retrieval_document", output_dimensionality=768)` | 維度 = 768 |
| L2 長度（未正規化） | 0.5842（與原型第一階段實測的「約 0.59」一致） |
| `task_type` 大小寫 | 小寫字串（`retrieval_document` / `retrieval_query`）可直接使用 |
| `genai.embed_content_async()` | 存在且可用，維度同樣為 768 |
| `GenerativeModel(system_instruction=...).generate_content_async()` | 可用，`temperature=0` 生效 |

三項 Gate 全數對齊「任一 gate 失敗就退回 `google-generativeai==0.8.6`」的預案，
**不需要重新校準 `RETRIEVAL_MIN_SCORE`**——L2 長度與第一階段實測值一致，代表兩側正規化與
`task_type` 不對稱策略的實際行為與原型時期相同。

**為何不選另一個方案**：
- 不選 `google-genai`：Gate 1 的失敗是套件宣告的硬性下限，不是暫時性的解析問題，等它未來
  放寬下限也不會回溯到現在——現在必須用會過 Gate 1 的版本。
- 不選 LangChain（`langchain-google-genai`）：v2 只需要一次 prompt、一次呼叫，LCEL 的
  串接與 prompt 模板管理在這裡不產生價值，只多一層要理解的抽象。第一階段的 LangChain
  技術棧仍完整保留在 `employee-portal-chatbot` 的 repo 裡，作品集關鍵字不會消失。

**已知風險**：`google-generativeai` 套件本身在 import 時會丟出
`FutureWarning: All support for the google.generativeai package has ended`。
這是一句警告不是錯誤，不影響功能，但記錄在 `docs/PITFALLS.md`，避免下一個維護者誤以為是
本專案的程式碼寫錯。批 B 或未來若要升級，必須等 `google-genai` 放寬 `pydantic` 下限、
或 v2 的 `pydantic` 鎖定版本本身升級到 `>=2.12.5` 之後再重跑本探針。

## Decision 2：prompt 以字串常數自行組裝

不選 `ChatPromptTemplate`：`{context}` 佔位符與語料裡的大括號要轉義，多一個會頻繁破壞
相容性的相依，而它只替我們做了 f-string 的事。系統提示與 human prompt 均為模組層級的
字串常數，由 `chat_prompt.py` 的純函式組裝。

## Decision 3：向量參數以 `$1::text::vector` 傳遞，不註冊 pgvector codec

**不選**在連線池的 `_init_connection`（`app/config/database.py`）註冊 pgvector codec。

**為何不選**：註冊 codec 會讓每一條池連線在建立時就依賴 `vector` 型別存在。正式資料庫若
還沒跑過 migration（`docs/PITFALLS.md` G4：push 不會自動更新雲端資料庫），`init_pool()`
會直接失敗，**整個入口網站起不來**，而不只是 AI 助理壞掉——這是「新功能的資料庫依賴」
汙染「既有功能可用性」的典型失敗模式。

**改採**：`policy_repository.py` 的每一條 SQL 把向量參數以 `$1::text::vector` 的方式
轉型，Python 端傳純文字（`"[0.1,0.2,...]"`）。失敗面被限制在單一端點：即使
`policy_embeddings` 表或 `vector` extension 不存在，只有 `/api/chat` 回 503，其他端點
不受影響。副作用是連 `pgvector` 這個 Python 套件都不必加進 `requirements.txt`
（只用官方 SQL 語法，不需要 asyncpg 的型別編解碼器）。

## Decision 4：`policy_embeddings` 不列入 `BUSINESS_TABLES`

`BUSINESS_TABLES`（`app/config/tables.py`）會被種子載入 `TRUNCATE`，且正式環境有 15 分鐘
閒置自動重置（`app/jobs/demo_auto_reset.py`）。若把 `policy_embeddings` 放進去：

- **失敗情境**：面試官提問後 15 分鐘沒有其他人使用系統，閒置重置觸發，`policy_embeddings`
  被清空，AI 助理對任何問題都回「查無相關規定」——看起來像功能正常但答不出來，且沒有任何
  錯誤訊息可供診斷。重建語料要重打數十次 embedding API，不是免費的操作。

**為何不選**：這個失敗必然發生（展示環境本來就會閒置），不是邊界情況。改為在
`tables.py` 只加註解說明原因，清單本身不動。

## Decision 5：本機與 CI 的 Postgres 影像改用 `pgvector/pgvector:pg16`

**不選**在 migration 裡吞掉 `CREATE EXTENSION IF NOT EXISTS vector;` 的錯誤（例如包一層
`try/except` 忽略失敗）。

**為何不選**：吞掉錯誤會讓 schema 在「有 vector extension」與「沒有」之間分岔——本機開發
用官方 pgvector 影像測試全綠，但如果哪個環境的 Postgres 影像忘了換，migration 階段不會
報錯，等到 `/api/chat` 真正執行查詢時才用一個很難聯想到「影像沒換」的錯誤訊息炸掉。
**測試綠燈不代表正式環境正確**，這正是本專案「後端測試打真實 PostgreSQL」這條規則要防的
同一類問題（規則的精神是不讓 mock／簡化掉的環境差異蓋過真實行為）。

改為讓 `CREATE EXTENSION` 保持不吞錯誤：影像沒換的話，migration 階段就會失敗，
失敗訊息直接指向 extension 不存在，而不是等到查詢階段才安靜地壞掉。
`pgvector/pgvector:pg16` 與官方 `postgres:16` 同為 PG16，既有 volume 相容。

## Decision 6：回應為一次性 JSON，不做 SSE 串流

既有的 axios instance（`frontend/src/api/client.js`）不支援 SSE，要串流就得繞過它，
連帶繞過 Bearer token 攔截器與慢請求追蹤，等於在既有 API 層旁邊開第二條路——違反本 change
「不得更動既有邏輯」的改動紀律。代價是使用者要等 1～3 秒才看到整段回答（冷啟動時更久，
見風險 3）。

## Decision 7：不擴充 `SimpleMarkdown`，改以系統提示約束 LLM 輸出格式

`SimpleMarkdown.jsx` 只支援標題、`-`／`*` 條列、`**粗體**`、行內程式碼、引言、段落，
不支援表格、不支援 `1.` 數字清單。四個理由選擇不擴充它而非在下游補救：

1. 它同時服務登入頁的使用手冊，改它就是改既有 UI 行為，違反改動紀律。
2. 它的段落緩衝語意是踩坑後才修好的（見元件內註解），加數字清單解析要動分支順序與
   `flushList` 的型別，是這個檔案裡迴歸風險最高的一段。
3. 語料本身通篇 `-` 條列，第一階段 72 題的回答格式已與這個渲染器相容，問題只出在 LLM
   偶爾自己加編號。**把約束下在源頭（系統提示規則 5）比在下游補救便宜得多**。
4. 表格在 375px 手機寬度本來就不可讀，擴充渲染器也解決不了可讀性問題。

保險做法是新增 `utils/chatMarkdown.js`（不碰 `SimpleMarkdown.jsx`）：渲染前把
`1. ` / `1) ` 開頭的行降級成 `- `，並把「— 依據：」那幾行切出來單獨用 chips 呈現。

## Decision 8：測試打真實 PostgreSQL，但 LLM 以注入的假 client 取代

v2 禁止 mock 的是「資料庫」，因為風險集中在 SQL 語意本身（UPSERT 覆蓋語意、排除約束、
唯一鍵衝突、時區轉換）。本 change 的 SQL 語意（相似度排序、門檻過濾、UPSERT、刪孤兒、
`vector` 型別轉換）全部仍打真實資料庫，被替換的只有對 Gemini 的 HTTP 外呼——那不是 v2
的風險所在，且真打會讓 CI 依賴外部配額（第一階段實測一輪 eval 144 次呼叫、會撞 429，
CI 環境沒有重試等待的餘裕）。注入方式用 `app.dependency_overrides`，不用 monkeypatch
模組屬性——後者容易在測試之間互相汙染，且無法反映 FastAPI 實際的 dependency 解析路徑。

## Decision 9：限流狀態放行程記憶體，用 `time.monotonic()`

**不選虛擬時鐘**：虛擬時間在到達 clamp 上限（2026-08-31）後就不再前進，限流視窗永遠不會
滑動——與 `docs/PITFALLS.md` B4（閒置重置計時器）是同一個失敗模式：只要展示環境的虛擬
時鐘走到視窗末端，所有使用者都會被永久鎖在限流狀態，且無法自行恢復。

**不選 Redis**：單一實例的展示站不值得多引入一個服務，`rate_limit.py` 的
`check_and_record(key, limit)` 用行程內的 dict + 時間戳陣列即可實作滑動視窗。

## Decision 10：語料放 `db/policy_docs/`，ingest 做成 db_scripts CLI + npm script，不併進 `db:reset`

**不選放 `docs/`**：那裡是專案文件目錄，混進語料會讓「改文件」與「改語料」兩件性質完全
不同的事在檔案總管裡看起來一樣，容易被連動修改工具或人工誤觸。

**不選併進 `db:reset`**：`db:reset` 是 e2e 測試前的例行動作，跑一次就會呼叫一次 embedding
API；e2e 在 CI 裡每次 push 都跑，併進去等於每次 CI 都燒一次配額，且 CI 本來就沒有設定
`GOOGLE_API_KEY`（見 Decision 8），ingest 在 CI 環境會直接失敗。

## Decision 11：批 A 刻意不把「今天是哪一天」注入 prompt

語料是靜態規則文件（考勤規則、請假辦法、產品目錄、公司簡介），沒有一題的正確答案需要
知道「今天」。一旦注入日期就必須走虛擬時鐘（`get_virtual_now()` 是非同步函式，需要資料庫
連線），多一個依賴虛擬時鐘的地方，就多一個之後有人不小心寫成 `datetime.now()` 的機會。
批 B（個人出勤查詢）需要日期時，由工具層（function calling）提供，不會影響批 A 的系統
提示。

## Decision 12：對話歷史只存前端 state，不落地資料庫、不做多輪上下文

落地會新增一張表：進 `BUSINESS_TABLES` 會被 15 分鐘展示重置清掉（見 Decision 4 的
同類失敗）；不進去又會在展示環境無限增長，沒有任何清理機制。72 題黃金題庫本身就是
單輪問答設計，已足夠涵蓋批 A 的驗收範圍。

## Decision 13：開放「依據來自資料」的推算，取代第一版的一律禁止

**第一版的做法**：系統提示規則 2 禁止模型輸出任何未逐字出現在片段中的數字，
理由是「引用來源正確、數字卻是自己算出來的答案，比答不出來更危險」。

**為什麼要推翻**：實機試用發現這個約束過度到損害功能本身。使用者問「我 9:20
打卡算遲到嗎？」，語料裡白紙黑字寫著「09:11:00 才算遲到」，模型在回答中也複述了
這句話，卻仍然說「片段中並未直接列出應到班時間與緩衝的具體數值，因此無法直接
回答」——它連「9:20 晚於 9:11」這個比較都不敢做。RAG 的語料不可能窮舉所有數值
案例（否則要建一堆向量資料庫），若連規則套用都不准，助理就只能當文件複讀機。

**新的界線是「推算的依據從哪裡來」，不是「有沒有算」**：

- 依據都在提供的資料裡 → 應該算出結論（比較與區間判斷、單位換算、級距對照遞增）
- 依據不在資料裡 → 不得發明（例如語料完全沒寫加班費怎麼算，就不能自己套公式）
- 前提不明確 → 給條件式回答並標明前提，不是拒答

**為何不選其他方案**：
- 不選「維持禁止、改為擴充語料窮舉案例」：使用者的提問組合是開放集合（任意打卡
  時間、任意年資、任意加班時長），窮舉不可能收斂，且語料每長一分，檢索精準度與
  維護成本都會惡化。
- 不選「開放推算但不加但書」：推算的前提（當天班表、是否有已核准請假、是哪一週）
  模型無從得知。**失敗情境**：使用者當天上午請了半天假，應到班時間其實是 13:00，
  模型卻依預設的 09:00 判定他 9:20 打卡算遲到——使用者因為看到肯定的答覆而不再
  去系統確認。因此規則 2 硬性要求推算結果必須附上「以系統實際顯示為準」，
  eval 也新增一項但書檢查守住這條。

## Decision 14：檢索落空改走受限的 fallback 提示，不再回制式拒答

原設計「檢索為空則短路、完全不呼叫 LLM」（Requirement 3 舊版）的初衷是防幻覺：
沒有依據的生成就是編造。但這條規則讓所有非政策問答的輸入都掉進同一個出口——
使用者輸入「早安」、抱怨工作壓力、或問「我的薪水多少」，一律得到「文件中查無
相關規定。」，像在查字典而不是對話。

改為：檢索落空時以 `FALLBACK_PROMPT` 呼叫模型，該提示**明確禁止產生任何具體
規定、時間、天數、金額或計算方式**，只被允許寒暄、同理與引導（建議找人資或主管、
或指向系統對應功能頁）。

**為何不選其他方案**：
- 不選「用關鍵字比對判斷打招呼」：情緒表達無法窮舉，關鍵字清單必然掛一漏萬。
- 不選「在檢索前先做一次意圖分類」：多一次 LLM 呼叫等於每則訊息都變慢，與這次
  的效能目標直接衝突。落空後才呼叫，只有真的沒命中的訊息付出這個成本。
- **失敗情境（若誤用政策提示走這條路）**：模型沒有任何檢索依據，卻拿到「你是政策
  問答助理」的指示，會憑記憶編造公司規定。因此 `test_chat.py` 有一條測試專門斷言
  落空路徑用的是 `FALLBACK_PROMPT` 而非 `SYSTEM_PROMPT`。

## Decision 15：互動式問答不做主動節流，配額保護交給每使用者限流

`GEMINI_REQUESTS_PER_MINUTE`（預設 10，即每次呼叫至少間隔 6 秒）是從第一階段原型
繼承的設定，那裡的情境是 eval 連續跑 72 題的批次作業。把它套在互動路徑上，使用者
每問一題就被迫多等數秒，卻不知道系統在等什麼。

改為 `GeminiClient(throttled=False)` 供 `/api/chat` 使用，ingest 與 eval 維持節流。
互動路徑的配額保護由既有的 `CHAT_RATE_LIMIT_PER_MINUTE` 負責。

**為何不選其他方案**：不選「直接調高 RPM 設定值」——那會同時弱化批次作業的保護，
而批次作業正是最容易撞配額的地方（一次 ingest 61 個 chunk、一輪 eval 77 題）。
兩種場景的需求相反，用同一個旋鈕調不出兩邊都對的值。

> 實測補充：關閉節流後量測真實 API 延遲，同樣的輸入在 1.5～8.4 秒之間跳動，且
> **長 prompt 未必比短 prompt 慢**（真實長度 1661+2279 字的請求量到 1.50 秒，
> 極短 prompt 反而量到 8.36 秒）。延遲主因是免費層本身的抖動，不是輸入長度，
> 因此**沒有**為了效能去精簡系統提示——那會犧牲約束力卻換不到速度。
> `GEMINI_TIMEOUT_SECONDS` 由 25 放寬到 40 以降低偶發的 `CHAT_UNAVAILABLE`。

## 風險與緩解

見 `tasks.md` 驗收前的風險清單（沿用計畫原文的 15 項，含相依衝突、Render 記憶體、
冷啟動疊加延遲、Gemini 速率限制、展示帳號成本濫用、prompt injection、Neon 手動步驟
遺漏、embedding 維度三處必須一致、`RETRIEVAL_MIN_SCORE` 綁死於特定模型組合、docker
volume 未重建、CI 兩個 job 都要改影像、語料與 v2 業務規則一致性、公司名稱不一致、
LLM 仍可能輸出表格、log 隱私）。

## 為批 B 鋪路

- `chat.ask()` 收整包 `current_user` 而不是只收 `user_id`——批 B 的個人查詢需要 `role` 與
  `department_id` 做 deny-by-default 範圍限縮。
- 回應帶 `answer.kind`（批 A 恆為 `"policy"`），前端 `ChatMessage` 寫成依 kind 分支的形狀。
- `gemini.py` 的 `generate()` 簽名預留 `tools=None` 參數位，批 B 的 function calling
  從這裡進來。
- 檢索與問答拆成兩支 service，批 B 在 `chat.ask()` 內加意圖分流、政策分支原封不動——把
  「批 B 不能弄壞批 A」變成結構性保證，不是靠自律。
- 系統提示拆成獨立常數，批 B 新增工具規則常數與既有規則組合，不必編輯已被 72 題驗證過
  的字串。
- `rate_limit.check_and_record(key, limit)` 是通用介面，批 B 的工具查詢可以用自己的
  key／配額重用同一支函式。
- `questions.yaml` 的 `category` 欄位讓批 B 能只跑新題組快速迭代，也能一次跑全部做迴歸。
- 批 B 的個人資料一律走既有 service 函式，不新寫 SQL——出勤必須走既有的生效值解析函式
  （`SPEC.md` §4.2：`attendances` 只存原始打卡事實，補打卡與請假核准不覆寫該表），
  否則助理的答案會跟畫面不一致。界線畫在這裡：AI 功能不得繞過既有業務層。
