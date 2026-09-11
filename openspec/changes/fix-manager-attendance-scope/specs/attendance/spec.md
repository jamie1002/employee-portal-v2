# Spec Delta：出勤明細的查詢範圍

## MODIFIED Requirements

### Requirement: 出勤明細查詢的角色範圍

`GET /api/attendance` SHALL 開放給 `admin` 與 `manager` 兩種角色，其餘角色一律回 403。
範圍限縮 MUST 採 deny-by-default：非 `admin` 的請求者一律限縮在自己所屬部門，不得寫成
「是 `manager` 才限縮」。

#### Scenario: 管理員查詢全公司

- **GIVEN** 以 `admin` 身分登入
- **WHEN** 呼叫 `GET /api/attendance` 且未指定 `department_id`
- **THEN** 回應 200，內容涵蓋全公司所有員工的出勤明細

#### Scenario: 主管查詢自己的部門

- **GIVEN** 以 `manager` 身分登入，所屬部門為研發部
- **WHEN** 呼叫 `GET /api/attendance` 且未指定 `department_id`
- **THEN** 回應 200，內容只包含研發部成員的出勤明細，不含其他部門任何一筆

#### Scenario: 主管指定自己的部門

- **GIVEN** 以 `manager` 身分登入，所屬部門為研發部
- **WHEN** 呼叫 `GET /api/attendance?department_id=<研發部>`
- **THEN** 回應 200，結果與未指定 `department_id` 時相同

#### Scenario: 一般員工一律被擋

- **GIVEN** 以 `employee` 身分登入
- **WHEN** 呼叫 `GET /api/attendance`
- **THEN** 回應 403

### Requirement: 主管的跨部門查詢一律拒絕

當 `manager` 指定的查詢對象不屬於自己的部門時，後端 SHALL 回應 403，且 MUST NOT 回傳
任何一筆資料。未指派部門的 `manager` SHALL 一律回應 403，MUST NOT 因為沒有可限縮的範圍
而放行成全公司。

#### Scenario: 主管指定他部門的成員

- **GIVEN** 以 `manager` 身分登入，所屬部門為研發部
- **WHEN** 呼叫 `GET /api/attendance?user_id=<業務部成員>`
- **THEN** 回應 403

#### Scenario: 主管指定他部門

- **GIVEN** 以 `manager` 身分登入，所屬部門為研發部
- **WHEN** 呼叫 `GET /api/attendance?department_id=<業務部>`
- **THEN** 回應 403

#### Scenario: 邊界——未指派部門的主管

- **GIVEN** 以 `manager` 身分登入，且 `department_id` 為 `NULL`
- **WHEN** 呼叫 `GET /api/attendance`
- **THEN** 回應 403，且回應內容不含任何出勤資料

#### Scenario: 主管指定自己部門內的成員

- **GIVEN** 以 `manager` 身分登入，所屬部門為研發部
- **WHEN** 呼叫 `GET /api/attendance?user_id=<研發部成員>`
- **THEN** 回應 200，只包含該成員的出勤明細

### Requirement: 出勤明細與出勤異動共用同一份範圍判斷

出勤明細（`GET /api/attendance`）與出勤異動（`GET /api/attendance/changes`）的可見範圍
解析 MUST 由同一個函式提供，不得各自實作。兩支端點對同一個請求者 SHALL 解析出相同的
可見成員集合。

#### Scenario: 同一位主管在兩支端點看到相同的成員範圍

- **GIVEN** 以 `manager` 身分登入，所屬部門為研發部
- **WHEN** 分別呼叫 `GET /api/attendance` 與 `GET /api/attendance/changes`
- **THEN** 兩者回應皆為 200，且出現在結果中的 `user_id` 集合不超出研發部成員

## ADDED Requirements

### Requirement: 部門出勤頁對主管開放

`/admin/attendance` 頁面 SHALL 對 `admin` 與 `manager` 開放，側邊選單 SHALL 對這兩種角色
顯示入口。頁面標題 SHALL 依角色切換：`admin` 顯示「全公司出勤」，`manager` 顯示「部門出勤」。
主管的部門篩選 SHALL 呈現為唯讀、鎖定在自己的部門，MUST NOT 提供切換到其他部門的操作。

#### Scenario: 主管看到部門出勤入口

- **GIVEN** 以 `manager` 身分登入
- **WHEN** 檢視側邊選單
- **THEN** 出現「部門出勤」項目，點擊後進入該頁並看到自己部門的出勤明細

#### Scenario: 主管無法切換部門

- **GIVEN** 以 `manager` 身分進入部門出勤頁
- **WHEN** 檢視篩選區
- **THEN** 部門欄位顯示自己的部門名稱且不可變更，員工下拉只列出同部門成員

#### Scenario: 管理員維持原有行為

- **GIVEN** 以 `admin` 身分進入該頁
- **WHEN** 檢視篩選區
- **THEN** 標題為「全公司出勤」，部門欄位為可選的下拉，含「全公司」選項

#### Scenario: 一般員工看不到入口

- **GIVEN** 以 `employee` 身分登入
- **WHEN** 檢視側邊選單
- **THEN** 不出現該頁入口；直接輸入網址時頁面不渲染任何出勤內容

#### Scenario: 響應式——375px 寬度下的主管篩選區

- **GIVEN** 以 `manager` 身分進入部門出勤頁，視窗寬度為 375px
- **WHEN** 檢視篩選區
- **THEN** 唯讀的部門標籤與其餘篩選欄位各自佔滿整行垂直堆疊，頁面不出現水平捲軸
