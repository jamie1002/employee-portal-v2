# Proposal：主管可檢視所屬部門的出勤明細

## Why

同一份部門出勤資料，主管**匯得出來卻看不到**。

- `POST /api/exports/attendance` 掛的是 `require_permission("exports.run", roles=("admin", "manager"))`，
  `export._scope_filters()` 會把非 admin 強制限縮成請求者自己的部門。`SPEC.md` §4.8 明文
  規定「非 `admin` 一律強制注入請求者的 `department_id`」，也就是**規格本來就預期主管會用
  這支端點取得自己部門的出勤資料**，而且連生效值（`attendance` kind）都在範圍內。
- 但讀取端點 `GET /api/attendance` 掛的是 `require_roles("admin")`，主管一律 403；
  前端 `/admin/attendance` 的 `RoleGate` 與側邊選單也只放行 admin
  （`docs/UI-SPEC.md` §3.14、路由表第 11 列）。

結果是主管能把部門出勤下載成 `.xlsx` 逐列翻閱，卻不能在畫面上看同一份資料。這不是刻意的
安全邊界，是漏掉的一塊：`SPEC.md` §3.1 權限矩陣的「上下班打卡」列把主管寫成「僅限本人打卡
與紀錄檢視」，與 §4.8 的匯出範圍規定互相矛盾。

修這個不一致同時是 AI 個人資料查詢（批 B）的前置條件。批 B 定下的原則是「AI 查得到的範圍
等於該角色在前端看得到的範圍」，若在錯誤的權限基準上實作，之後修好還得回頭改工具層。

對應章節：`SPEC.md` §3.1（權限矩陣）、§3.2（範圍限縮 deny-by-default）、§4.2（生效值解析）、
§4.8（匯出範圍）、§6.x（出勤端點）；`docs/UI-SPEC.md` §3.14、路由表。

## What Changes

- `GET /api/attendance` 開放給 `manager`，範圍限縮在 service 層處理：非 admin 一律限縮成
  請求者自己的部門，指定他部門成員回 403。
- 把既有 `attendance_changes.get_changes()` 裡那段「依角色解析可見的 user_ids」抽成共用
  函式，讓出勤明細與出勤異動**共用同一份權限語意**，避免出現第二套實作
  （`docs/PITFALLS.md` C1：權限判斷分散成多份實作是這個專案記錄過的失敗模式）。
- 前端 `/admin/attendance` 對主管開放。主管看到的部門篩選鎖死自己的部門，頁面標題與
  空狀態文案依角色切換（主管看到的是「部門出勤」而非「全公司出勤」）。
- 更正 `SPEC.md` §3.1 權限矩陣與 `docs/UI-SPEC.md` §3.14 與路由表。

**不做**：不動 `export._scope_filters()`（理由見 `design.md` Decision 3）；不改路由路徑；
不開放主管查詢他部門；不開放員工查詢任何他人資料。

## Impact

新增：

- `backend/app/services/attendance_scope.py`
- `backend/tests/test_attendance_scope.py`

修改：

- `backend/app/routers/attendance.py`（`GET /api/attendance` 的權限 dependency 與參數傳遞）
- `backend/app/services/attendance.py`（`get_all()` 改收 `current_user` 並走共用範圍限縮）
- `backend/app/services/attendance_changes.py`（改用抽出的共用函式）
- `backend/app/schemas/attendance.py`（`parse_company_attendance_query` 的參數語意）
- `backend/tests/test_attendance.py`、`backend/tests/test_attendance_changes.py`
- `frontend/src/pages/admin/CompanyAttendancePage.jsx`
- `frontend/src/components/AppShell.jsx`（選單 `roles`）
- `frontend/src/pages/admin/CompanyAttendancePage.test.jsx`
- `e2e/` 既有出勤相關情境（主管視角）
- `SPEC.md` §3.1、§6.x；`docs/UI-SPEC.md` §3.14 與路由表；`docs/PITFALLS.md`（新增一則）
