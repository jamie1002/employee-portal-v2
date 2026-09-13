# Tasks：AI 助理的個人資料查詢（批 B）

## 0. 探針（已完成）

- [x] 0.1 驗證 `google-generativeai==0.8.6` 支援 function calling → 通過
- [x] 0.2 驗證 `gemini-3.1-flash-lite` 會產生正確的工具呼叫與參數 → 通過
- [x] 0.3 量測兩輪往返延遲 → 2.5～4.8 秒，推翻「延遲翻倍」的預估
- [x] 0.4 比較 3.1 與 3.5 的工具呼叫準確度（各 3 次重複）→ 打平，維持 3.1
- [x] 0.5 探針結果寫入 `design.md` Step 0 與 `docs/PITFALLS.md` I11 後續

## 1. SDK 層：工具往返

- [x] 1.1 `utils/gemini.py` 新增 `generate_with_tools(system_instruction, user_content,
      tools)`：回傳「模型要呼叫哪些工具」或「最終文字」，不在這一層決定要不要執行工具
- [x] 1.2 新增 `continue_with_tool_results(...)`：把工具結果送回模型取得最終文字
- [x] 1.3 `config/settings.py` 新增 `CHAT_TOTAL_TIMEOUT_SECONDS`（整趟上限，預設 60）；
      工具往返上限為一輪，這是結構性的（拿到結果就要文字回答），不做成設定值

## 1t. SDK 層測試

- [x] 1t.1 模型回傳工具呼叫時，`generate_with_tools()` 正確解析出名稱與參數
- [x] 1t.2 模型直接回文字時，回傳文字且工具呼叫清單為空
- [x] 1t.3 上游例外一律轉 `GeminiUnavailable`

## 2. 工具層：宣告與派工

- [x] 2.1 `services/chat_tools.py` 定義四支個人工具的宣告：`get_today_status`、
      `get_my_attendance_summary`、`get_my_leave_quota`、`get_my_requests`
- [x] 2.2 `build_declarations(current_user)` 依角色組裝清單（第一階段全角色相同）
- [x] 2.3 `execute(pool, current_user, name, args)` 派工到既有 service，
      **不寫任何 SQL**；未知或不該給該角色的工具名稱一律回結構化拒絕訊息
- [x] 2.4 聚合函式：把 `get_my_records()` 的結果算成出勤天數、遲到、早退、缺勤、
      請假天數與至多 10 筆明細，狀態判定沿用 `attendance.matches_status_filter()`
- [x] 2.5 日期參數解析與驗證（格式錯誤回結構化錯誤讓模型重問，不用預設值瞎猜）

## 2t. 工具層測試

- [x] 2t.1 四支工具各自回傳正確結構，且數字與對應 service 直接呼叫的結果一致
- [x] 2t.2 **「正常」的統計排除早退與未打下班卡的日子**，與出勤頁篩選結果相同
- [x] 2t.3 未知工具名稱回拒絕訊息而非拋例外
- [x] 2t.4 日期格式錯誤回結構化錯誤
- [x] 2t.5 工具層不自行撰寫 SQL 的驗證：`chat_tools.py` 不得出現 `pool.fetch`／
      `pool.execute` 等直接查詢（單純的主鍵查表走 repository 是 service 層的正常作法）

## 3. 問答流程串接

- [x] 3.1 `chat_prompt.py` 新增 `TOOL_RULES` 常數（工具數據不加但書、越權以人話說明、
      找不到人時怎麼講），與既有 `SYSTEM_PROMPT` 組合，**不編輯既有字串**
- [x] 3.2 系統提示注入「今天是哪一天」，取自 `get_virtual_now()`
- [x] 3.3 `chat.ask()` 在既有政策路徑上掛工具清單；模型不呼叫工具時走原路徑不變
- [x] 3.4 模型呼叫工具時：執行 → 回送結果 → 取得最終文字，`kind` 設為 `"personal"`
- [x] 3.5 工具往返次數上限與整趟逾時
- [x] 3.6 `_log()` 擴充：記工具名稱、成功與否、耗時，**不記參數與回傳內容**

## 3t. 問答流程測試

- [x] 3t.1 政策提問不觸發工具，`kind` 仍為 `policy`（批 A 迴歸）
- [x] 3t.2 個人提問觸發工具，`kind` 為 `personal`
- [x] 3t.3 模型要求呼叫工具時，後端只跑一輪就要求產生文字，不給第二次機會
- [x] 3t.4 整趟逾時回 503 `CHAT_UNAVAILABLE`
- [x] 3t.5 log 不含工具參數與個人資料

## 4. 第一階段驗收（四支個人工具）

- [x] 4.1 `npm run test:backend` 全綠
- [x] 4.2 `npm run eval:chat` 六項門檻全綠（**帶工具後的批 A 迴歸，硬性條件**）——
      推算但書門檻改為 85% 並把分母從 6 加到 12，理由見 `run_eval.py`
- [x] 4.3 本機實際對話驗證（三個角色各走一遍，抓到一個三層測試與 eval 都沒抓到的
      權限文案 bug，見 `docs/PITFALLS.md` I14）

## 5. 團隊工具（第二階段）

- [x] 5.1 新增 `get_pending_reviews`（manager、admin），包三支 `*.get_pending()`
- [x] 5.2 新增 `get_team_attendance_summary`（manager、admin），包 `attendance.get_all()`，
      `department_name` 只出現在 admin 的宣告裡
- [x] 5.3 姓名解析：`employee_name` → user_id，查無回「找不到這位同事」、
      同名多筆回「請改用出勤查詢頁指定」，解析後仍走 `attendance_scope`
- [x] 5.4 部門名稱解析：`department_name` → department_id，查無時明確回報

## 5t. 團隊工具測試

- [x] 5t.1 employee 的工具清單不含這兩支
- [x] 5t.2 manager 的 `get_team_attendance_summary` 宣告不含 `department_name`
- [x] 5t.3 **偽造的工具呼叫**：employee 身分送 `get_team_attendance_summary`，
      工具層擋下且不回傳任何他人資料
- [x] 5t.4 manager 查他部門成員回拒絕訊息（走 `attendance_scope` 的 403）
- [x] 5t.5 查無此人、同名多筆各自回對應訊息
- [x] 5t.6 admin 可查指定部門與全公司

## 6. eval 題組

- [x] 6.1 `questions.yaml` 補五題推算題把但書分母拉到 12（跨午休請假、多日請假、
      加班捨去與整除、特休上限外推），期望值一律由既有業務函式現算
- [x] 6.2 新增權限題組四題（employee／manager×2／admin），含 `forbid_leak`
- [x] 6.3 `run_eval.py` 支援 `as_role`，新增「越權題未洩漏他人資料」門檻（固定 100%）

## 7. 前端

- [x] 7.1 `ChatPage.jsx` 移除「個人出勤紀錄、假別剩餘量與申請進度請至對應功能頁查詢」
      這行免責（批 A 埋的伏筆）
- [x] 7.2 空狀態建議問題加入個人類範例，且依角色給不同範例
- [x] 7.3 `ChatMessage.jsx` 確認 `kind="personal"` 走既有的 markdown 渲染分支

## 7t. 前端測試

- [x] 7t.1 免責文案已移除
- [x] 7t.2 `kind="personal"` 正常渲染
- [x] 7t.3 依角色顯示不同的建議問題

## 8. e2e

- [x] 8.1 建議問題依角色切換（員工看不到團隊題、主管看到部門題、管理員看到全公司題）
- [x] 8.2 免責文案已拆除
- 註：原本規劃的「實際問答拿到含數字的回答」**刻意不進 e2e**。既有的 `chat.spec.js`
  已經定調 happy path 不進 e2e（依賴外部服務、慢、不穩），由 `backend/eval` 負責。
  改成測這一層真正該測又不需要 API 的東西：真實登入與真實角色串起來的畫面差異。

## 9. 文件

- [x] 9.1 `SPEC.md` §4.12 擴充批 B 範圍與工具清單、§6.8 補 `kind="personal"`
- [x] 9.2 `docs/UI-SPEC.md` §3.18 更新免責文案與建議問題
- [x] 9.3 `docs/PITFALLS.md` 新增批 B 實作期間的踩坑
- [x] 9.4 `.env.example` 補上 `CHAT_TOTAL_TIMEOUT_SECONDS` 的說明

## 10. 驗收

```bash
npm run test:backend
```

```bash
npm run test:frontend
```

```bash
npm run db:reset
```

```bash
npm run test:e2e
```

```bash
npm run eval:chat
```

```bash
npx openspec validate add-personal-data-chat --strict
```

三層測試全綠、eval 六項門檻全綠、且以三個展示帳號在畫面上各走一遍個人查詢與越權查詢，
才算完成。


---

## 11. 明天要做的事（2026-09-13 起）

### 11.1 唯一真正卡住的事：跑一次完整 eval

> **09-13 結果（兩輪完整 eval，詳見 PITFALLS I15、I16）**
>
> - **第一輪**：3 題紅，全是判定寫錯（權限說明被當成誘導題判定、姓名在題目裡被當洩漏）。
>   但存檔裡另有一題綠燈下的真退化：員工問「主管看得到其他部門的申請紀錄嗎？」被誤套
>   權限拒絕句（`fd8d136` 引入）→ 提示詞補對照例子修正（`03419ce`）。
> - **探針**另抓到員工點名問同事時，模型拿自己的紀錄回答 → 後端擋（`ebd0567`），題庫補一題（共 87 題）。
> - **第二輪**（最終程式碼與提示詞）：7/9 綠，2 紅仍是判定問題——權限說明沒附引用被算進引用率、
>   「不在你的權限範圍」這種說法沒被認出。修正判定後，以第二輪存下的 87 則回答**離線重判全綠**。
>   程式碼與提示詞在第二輪之後沒有再改，所以沒有再燒第三輪。
>
> **09-13 下午：使用者實測又發現四個問題，一起修（`02f1e0c`，詳見 PITFALLS I17、I18）**
>
> - 搜不到政策文件時不帶工具 → 「列出日期」「異動」這類問法回沒有權限
> - 明細只給最近 10 天 → 7 月異常日期列不出來；團隊工具沒有日期；沒有通訊錄工具
> - 過程中另修：打卡時間是 UTC、第二輪模型再要工具造成 503
> - 題庫改為 94 題（刪 1 加 8），新增工具使用／異常日期／通訊錄三項判定
> - **第三輪完整 eval**：只有引用率 74/75 紅，失敗的是閒聊題（「打卡」命中出勤規則走了
>   政策路徑，回應是同理與引導、本來就不該附引用）→ 判定排除閒聊題後以存檔離線重判全綠。
>   推算但書 10/11（91%）在 85% 門檻內。其餘各項 100%。

```bash
npm run eval:chat
```

**有兩件事都還沒有完整 eval 背書**，不是只有一件：

1. **權限題組（四題，含 `as_role` 與 `forbid_leak`）從來沒有實跑過。** 程式與題目都
   寫好也提交了，但沒有任何一次成功執行證明它們會通過，甚至沒證明過那四題不會讓
   腳本掛掉。
2. **`fd8d136`（主管被誤告知沒有權限的提示詞修正）也沒有一次完整的 eval。** 那次改動
   後啟動的那一輪跑到第 49 題就把配額用光，33 題拿到 429 而整輪判定失敗。已完成的
   49 題七項指標全部 100%，這是**部分證據，不是證明**——動系統提示必須有完整一輪。

最後一次完整通過的 eval 是合併第二階段之後、`fd8d136` 之前那一輪
（引用率 75/75、誘導題拒答 7/7、該答有答 75/75、數字正確 17/17、推算但書 11/11）。

配額是**每日**上限（embedding 1000 次／天），跨日自動重置。一輪 86 題約耗 86 次
embedding 加上一百多次生成，所以**一天最多安全跑三到四輪**，不要像 09-12 那樣連跑六輪。

預期結果：七項門檻全綠（hit@3、章節覆蓋率、引用率、誘導題拒答、該答有答、
數字正確、推算但書 ≥85%、越權未洩漏 100%）。

若權限題有紅，先用 `npm run eval:chat -- --category permission --save-answers <檔案>`
單獨跑那四題（只花四次 embedding），看完整回答再判斷是模型行為問題還是判定寫錯——
09-12 一天之內就遇過三次「判定寫錯」而不是模型答錯，不要預設是模型的錯。

### 11.2 使用者實機測試

本機環境用 `npm run dev` 或請 AI 開起來。三個展示帳號各走一遍：

- **一般員工**：問自己的出勤／特休／申請進度；問部門或全公司的資料應得到
  「你目前沒有權限查看」而不是「文件裡沒有」
- **主管**：問部門誰遲到最多（應查得到研發部）；問張大同（業務部）應被擋
- **管理員**：問全公司或指定部門（例如業務部）

**注意**：配額只影響 AI 的回答，系統其他功能不受影響。

### 11.3 雲端部署（eval 與實測都過之後）

**這次不需要任何資料庫步驟**——已確認 `git diff origin/main..main -- db/ backend/app/db_scripts/`
是空的，批 B 沒有新增 migration、沒有改語料，全部是唯讀查詢走既有資料表。
所以與批 A 上線流程不同，**不必跑 `db:migrate`，也不必跑 `db:ingest`**。

```bash
git push origin main
```

push 之後 Render 與 Vercel 自動部署。環境變數也不需要新增（`CHAT_TOTAL_TIMEOUT_SECONDS`
有預設值 60，不設也能跑）。

驗證：`curl https://employee-portal-api-107g.onrender.com/api/health` 應回
`"policy_chunk_count":61`，再用三個展示帳號在
`https://employee-portal-v2-frontend.vercel.app` 各問一題。

### 11.4 小修正：出勤頁的人員篩選標籤改成「員工」

> **09-13 已完成。** 實際改動比下表多：測試檔共 7 處（不是 3 處，同一題裡還有
> `toHaveValue` 與選項文字斷言），UI-SPEC §3.14 的元件表（「使用者下拉」那列）也要改。
> 前端測試 8/8 通過，本機畫面確認。

「全公司出勤」／「部門出勤」頁的人員篩選欄位目前叫「使用者」，應該改成「員工」。
**這不只是換個字**：同一個專案裡「匯出報表」頁用的一直是員工用語（員工資料、
員工編號、員工姓名），出勤頁用「使用者」是唯一的例外，兩邊不一致。

要一起改的四處（已盤點，範圍就這些）：

| 檔案 | 位置 | 現況 → 改成 |
| :--- | :--- | :--- |
| `frontend/src/pages/admin/CompanyAttendancePage.jsx` | 第 130 行 | 標籤「使用者」→「員工」 |
| 同上 | 第 138 行 | 下拉第一項「全部使用者」→「全部員工」 |
| `frontend/src/pages/admin/CompanyAttendancePage.test.jsx` | 第 76、107 行與該題測試名稱 | `getByLabelText("使用者")` 要跟著改 |
| `docs/UI-SPEC.md` | §3.14 第 271 行 | 篩選列順序「部門 → 使用者 → 狀態 → 起訖日期」→「部門 → 員工 → …」 |

e2e 沒有引用這個標籤，不受影響。改完跑 `npm run test:frontend` 即可，
不需要 API 配額，**所以這一項可以在配額恢復前先做掉**。

### 11.5 收尾

- `npx openspec validate add-personal-data-chat --strict`
- 全部通過後可考慮 `openspec archive add-personal-data-chat`
- `README.md` 的「雲端部署 → 後續維運」可補一句：批 B 這類純唯讀的功能變更，
  push 即可，不需要手動的資料庫步驟
