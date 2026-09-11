# Tasks：AI 助理的個人資料查詢（批 B）

## 0. 探針（已完成）

- [x] 0.1 驗證 `google-generativeai==0.8.6` 支援 function calling → 通過
- [x] 0.2 驗證 `gemini-3.1-flash-lite` 會產生正確的工具呼叫與參數 → 通過
- [x] 0.3 量測兩輪往返延遲 → 2.5～4.8 秒，推翻「延遲翻倍」的預估
- [x] 0.4 比較 3.1 與 3.5 的工具呼叫準確度（各 3 次重複）→ 打平，維持 3.1
- [x] 0.5 探針結果寫入 `design.md` Step 0 與 `docs/PITFALLS.md` I11 後續

## 1. SDK 層：工具往返

- [ ] 1.1 `utils/gemini.py` 新增 `generate_with_tools(system_instruction, user_content,
      tools)`：回傳「模型要呼叫哪些工具」或「最終文字」，不在這一層決定要不要執行工具
- [ ] 1.2 新增 `continue_with_tool_results(...)`：把工具結果送回模型取得最終文字
- [ ] 1.3 `config/settings.py` 新增 `CHAT_TOTAL_TIMEOUT_SECONDS`（整趟上限，預設 60）
      與 `CHAT_MAX_TOOL_ROUNDS`（預設 1）；`.env.example` 同步補上說明

## 1t. SDK 層測試

- [ ] 1t.1 模型回傳工具呼叫時，`generate_with_tools()` 正確解析出名稱與參數
- [ ] 1t.2 模型直接回文字時，回傳文字且工具呼叫清單為空
- [ ] 1t.3 上游例外一律轉 `GeminiUnavailable`

## 2. 工具層：宣告與派工

- [ ] 2.1 `services/chat_tools.py` 定義四支個人工具的宣告：`get_today_status`、
      `get_my_attendance_summary`、`get_my_leave_quota`、`get_my_requests`
- [ ] 2.2 `build_declarations(current_user)` 依角色組裝清單（第一階段全角色相同）
- [ ] 2.3 `execute(pool, current_user, name, args)` 派工到既有 service，
      **不寫任何 SQL**；未知或不該給該角色的工具名稱一律回結構化拒絕訊息
- [ ] 2.4 聚合函式：把 `get_my_records()` 的結果算成出勤天數、遲到、早退、缺勤、
      請假天數與至多 10 筆明細，狀態判定沿用 `attendance.matches_status_filter()`
- [ ] 2.5 日期參數解析與驗證（格式錯誤回結構化錯誤讓模型重問，不用預設值瞎猜）

## 2t. 工具層測試

- [ ] 2t.1 四支工具各自回傳正確結構，且數字與對應 service 直接呼叫的結果一致
- [ ] 2t.2 **「正常」的統計排除早退與未打下班卡的日子**，與出勤頁篩選結果相同
- [ ] 2t.3 未知工具名稱回拒絕訊息而非拋例外
- [ ] 2t.4 日期格式錯誤回結構化錯誤
- [ ] 2t.5 工具層不直接碰資料庫的驗證：`chat_tools.py` 不得 import 任何 repository

## 3. 問答流程串接

- [ ] 3.1 `chat_prompt.py` 新增 `TOOL_RULES` 常數（工具數據不加但書、越權以人話說明、
      找不到人時怎麼講），與既有 `SYSTEM_PROMPT` 組合，**不編輯既有字串**
- [ ] 3.2 系統提示注入「今天是哪一天」，取自 `get_virtual_now()`
- [ ] 3.3 `chat.ask()` 在既有政策路徑上掛工具清單；模型不呼叫工具時走原路徑不變
- [ ] 3.4 模型呼叫工具時：執行 → 回送結果 → 取得最終文字，`kind` 設為 `"personal"`
- [ ] 3.5 工具往返次數上限與整趟逾時
- [ ] 3.6 `_log()` 擴充：記工具名稱、成功與否、耗時，**不記參數與回傳內容**

## 3t. 問答流程測試

- [ ] 3t.1 政策提問不觸發工具，`kind` 仍為 `policy`（批 A 迴歸）
- [ ] 3t.2 個人提問觸發工具，`kind` 為 `personal`
- [ ] 3t.3 模型連續要求第二輪工具時，後端停止並要求產生文字
- [ ] 3t.4 整趟逾時回 503 `CHAT_UNAVAILABLE`
- [ ] 3t.5 log 不含工具參數與個人資料

## 4. 第一階段驗收（四支個人工具）

- [ ] 4.1 `npm run test:backend` 全綠
- [ ] 4.2 `npm run eval:chat` 六項門檻全綠（**帶工具後的批 A 迴歸，硬性條件**）
- [ ] 4.3 本機實際對話驗證四支工具

## 5. 團隊工具（第二階段）

- [ ] 5.1 新增 `get_pending_reviews`（manager、admin），包三支 `*.get_pending()`
- [ ] 5.2 新增 `get_team_attendance_summary`（manager、admin），包 `attendance.get_all()`，
      `department_name` 只出現在 admin 的宣告裡
- [ ] 5.3 姓名解析：`employee_name` → user_id，查無回「找不到這位同事」、
      同名多筆回「請改用出勤查詢頁指定」，解析後仍走 `attendance_scope`
- [ ] 5.4 部門名稱解析：`department_name` → department_id，查無時明確回報

## 5t. 團隊工具測試

- [ ] 5t.1 employee 的工具清單不含這兩支
- [ ] 5t.2 manager 的 `get_team_attendance_summary` 宣告不含 `department_name`
- [ ] 5t.3 **偽造的工具呼叫**：employee 身分送 `get_team_attendance_summary`，
      工具層擋下且不回傳任何他人資料
- [ ] 5t.4 manager 查他部門成員回拒絕訊息（走 `attendance_scope` 的 403）
- [ ] 5t.5 查無此人、同名多筆各自回對應訊息
- [ ] 5t.6 admin 可查指定部門與全公司

## 6. eval 題組

- [ ] 6.1 `questions.yaml` 新增 `category: personal` 題組（約 10 題），
      期望值由既有業務函式以虛擬時鐘固定錨點現算，**不寫死數字**
- [ ] 6.2 新增權限題組：同一句話用三種角色各問一次，驗證範圍差異與拒答
- [ ] 6.3 `run_eval.py` 支援以角色身分執行題目，並新增「越權題不得洩漏數字」的判定

## 7. 前端

- [ ] 7.1 `ChatPage.jsx` 移除「個人出勤紀錄、假別剩餘量與申請進度請至對應功能頁查詢」
      這行免責（批 A 埋的伏筆）
- [ ] 7.2 空狀態建議問題加入個人類範例，且依角色給不同範例
- [ ] 7.3 `ChatMessage.jsx` 確認 `kind="personal"` 走既有的 markdown 渲染分支

## 7t. 前端測試

- [ ] 7t.1 免責文案已移除
- [ ] 7t.2 `kind="personal"` 正常渲染
- [ ] 7t.3 依角色顯示不同的建議問題

## 8. e2e

- [ ] 8.1 員工提問個人出勤後得到含數字的回答
- [ ] 8.2 員工提問部門出勤後得到「沒有權限」的人話說明，畫面不出現錯誤橫幅

## 9. 文件

- [ ] 9.1 `SPEC.md` §4.12 擴充批 B 範圍與工具清單、§6.8 補 `kind="personal"`
- [ ] 9.2 `docs/UI-SPEC.md` §3.18 更新免責文案與建議問題
- [ ] 9.3 `docs/PITFALLS.md` 新增批 B 實作期間的踩坑
- [ ] 9.4 `.env.example` 補兩個新設定值的說明

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
