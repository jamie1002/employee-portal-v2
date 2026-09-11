# Spec Delta：AI 助理的個人資料查詢

## ADDED Requirements

### Requirement: 工具查詢的可見範圍等同該角色在前端的可見範圍

AI 助理的每一支查詢工具 MUST 呼叫既有的 service 函式取得資料，MUST NOT 自行撰寫 SQL。
工具可取得的資料範圍 SHALL 與該角色在對應功能頁看得到的範圍完全相同，出勤類查詢
MUST 經由 `attendance_scope.resolve_visible_user_ids()` 解析可見成員。

#### Scenario: 一般員工查詢自己的出勤

- **GIVEN** 以 `employee` 身分登入 AI 助理
- **WHEN** 提問「我八月遲到幾次」
- **THEN** 回應 200，內容只依據本人的出勤資料，數字與出勤紀錄頁篩選「遲到」的結果一致

#### Scenario: 主管查詢部門出勤

- **GIVEN** 以 `manager` 身分登入，所屬部門為研發部
- **WHEN** 提問「我部門這個月誰遲到最多」
- **THEN** 回應 200，統計範圍只涵蓋研發部成員，不含其他部門任何一人

#### Scenario: 主管查詢他部門成員一律被拒

- **GIVEN** 以 `manager` 身分登入，所屬部門為研發部
- **WHEN** 提問「張大同這個月出勤如何」，而張大同屬於業務部
- **THEN** 回應 200，助理說明無法查詢該同事的資料，回應內容 MUST NOT 包含任何張大同的出勤數字

#### Scenario: 管理員查詢全公司

- **GIVEN** 以 `admin` 身分登入
- **WHEN** 提問「這個月全公司誰缺勤最多」
- **THEN** 回應 200，統計範圍涵蓋全公司成員

### Requirement: 工具宣告依角色組裝，且工具層必須自行再次檢查權限

組裝給模型的工具清單 SHALL 依 `current_user["role"]` 過濾。工具執行層 MUST 自行驗證
權限，MUST NOT 假設「模型看不到該工具就不會呼叫」。當收到不在該角色清單內的工具名稱時，
後端 SHALL 拒絕執行並回傳結構化的拒絕訊息。

#### Scenario: 一般員工的工具清單不含團隊查詢

- **GIVEN** 以 `employee` 身分提問
- **WHEN** 後端組裝工具宣告
- **THEN** 清單中不存在 `get_team_attendance_summary` 與 `get_pending_reviews`

#### Scenario: 偽造的工具呼叫被工具層擋下

- **GIVEN** 以 `employee` 身分登入
- **WHEN** 模型輸出一個名為 `get_team_attendance_summary` 的呼叫請求
- **THEN** 後端不執行該工具，回傳結構化拒絕訊息給模型，且最終回應不含任何他人資料

#### Scenario: 主管的工具清單不含指定部門的參數

- **GIVEN** 以 `manager` 身分提問
- **WHEN** 後端組裝 `get_team_attendance_summary` 的宣告
- **THEN** 該宣告的參數不含 `department_name`

### Requirement: 查詢對象以姓名指定，不以編號指定

工具參數 MUST NOT 包含 `user_id` 或 `department_id`。要指定查詢對象時 SHALL 使用
`employee_name` 或 `department_name`，由後端解析為編號後再套用範圍限縮。解析結果為
多筆或查無資料時，後端 SHALL 回傳可讓助理說明情況的結構化訊息，MUST NOT 任選一筆。

#### Scenario: 查無此人

- **GIVEN** 以 `manager` 身分登入
- **WHEN** 提問「王大鎚這個月遲到幾次」，系統中沒有這個人
- **THEN** 回應 200，助理說明找不到這位同事，回應不含任何出勤數字

#### Scenario: 同名多人

- **GIVEN** 系統中有兩位同名的「陳小華」且皆屬於提問者的部門
- **WHEN** 主管提問「陳小華這個月出勤如何」
- **THEN** 回應 200，助理請使用者改用出勤查詢頁指定，MUST NOT 任選其中一位回答

### Requirement: 以虛擬時鐘的今天解析相對日期

系統提示 SHALL 注入「今天是哪一天」，其值 MUST 取自 `get_virtual_now()`，
MUST NOT 使用 `datetime.now()` 或資料庫的 `now()`。

#### Scenario: 相對日期以虛擬時鐘為準

- **GIVEN** 展示用虛擬時鐘被調整為 2026-08-24
- **WHEN** 使用者提問「我這個月遲到幾次」
- **THEN** 查詢區間為 2026-08-01 至 2026-08-31，與畫面顯示的展示時間一致

### Requirement: 統計由工具層計算，模型不重算

工具回傳給模型的 SHALL 是已聚合的統計結果與至多 10 筆代表性明細，MUST NOT 回傳完整的
原始出勤列。狀態判定 MUST 沿用 `attendance.matches_status_filter()`。

#### Scenario: 正常出勤天數與畫面一致

- **GIVEN** 某位使用者當月有一天狀態為 `normal` 但同時早退
- **WHEN** 提問「我這個月正常出勤幾天」
- **THEN** 助理回答的天數不把該日計入正常，與出勤紀錄頁篩選「正常」的筆數相同

### Requirement: 個人資料的回答不附「以系統實際顯示為準」

當數字來自工具回傳時，回答 MUST NOT 附加「以系統實際顯示為準」這類但書。當數字來自
政策文件的推算時，SHALL 依批 A 既有規則附上該但書。

#### Scenario: 工具數據不加但書

- **GIVEN** 使用者提問「我特休還剩幾天」
- **WHEN** 助理依 `get_my_leave_quota` 的回傳作答
- **THEN** 回答不含「以系統實際顯示為準」

#### Scenario: 政策推算仍加但書

- **GIVEN** 使用者提問「我 9:20 打卡算遲到嗎」且當日無打卡資料可查
- **WHEN** 助理依政策文件推算作答
- **THEN** 回答附上「以系統實際顯示為準」

### Requirement: 越權提問以對話說明，不以 HTTP 錯誤呈現

使用者提出超出其權限的查詢時，`/api/chat` SHALL 回應 200 並由助理以自然語言說明無法
查詢，MUST NOT 回應 403。

#### Scenario: 員工詢問部門出勤

- **GIVEN** 以 `employee` 身分登入
- **WHEN** 提問「我們部門今天誰遲到」
- **THEN** 回應 200，助理說明沒有權限查看並建議詢問主管或人資，畫面不顯示錯誤訊息

### Requirement: 工具往返有次數與整體時間上限

單次提問中模型 SHALL 最多進行一輪工具呼叫。整趟問答 MUST 受
`CHAT_TOTAL_TIMEOUT_SECONDS` 限制，逾時 SHALL 回應 503 並帶 `CHAT_UNAVAILABLE`。

#### Scenario: 超過一輪即停止

- **GIVEN** 模型在取得工具結果後又輸出一個新的工具呼叫請求
- **WHEN** 後端處理該回應
- **THEN** 後端不再執行任何工具，改以既有結果要求模型產生文字回答

#### Scenario: 整趟逾時

- **GIVEN** 上游延遲使整趟問答超過 `CHAT_TOTAL_TIMEOUT_SECONDS`
- **WHEN** 使用者送出提問
- **THEN** 回應 503 且 `code` 為 `CHAT_UNAVAILABLE`

### Requirement: 記錄不得包含個人資料

問答記錄 SHALL 只包含 `user_id`、問題長度、使用的工具名稱、工具是否成功、耗時。
MUST NOT 記錄工具參數、工具回傳內容、提問全文或回答全文。

#### Scenario: 工具參數不進記錄

- **GIVEN** 主管提問「陳小華上個月出勤如何」
- **WHEN** 系統寫入問答記錄
- **THEN** 記錄含工具名稱與耗時，不含「陳小華」或任何日期區間與出勤數字

### Requirement: 批 A 的政策問答行為不得退化

帶工具清單後，政策類提問 SHALL 維持單輪呼叫。`npm run eval:chat` 的六項門檻
（hit@3 ≥ 90%、引用率 100%、誘導題拒答率 100%、該答有答 100%、數字型答案 100%、
章節覆蓋率 100%）MUST 全數達標。

#### Scenario: 政策提問不觸發工具

- **GIVEN** 使用者提問「特別休假的天數怎麼計算」
- **WHEN** 模型收到政策片段與工具清單
- **THEN** 模型不呼叫任何工具，單輪產生回答，回應的 `kind` 為 `policy`

#### Scenario: 黃金題庫全綠

- **GIVEN** 批 B 實作完成
- **WHEN** 執行 `npm run eval:chat`
- **THEN** 六項門檻全數達標
