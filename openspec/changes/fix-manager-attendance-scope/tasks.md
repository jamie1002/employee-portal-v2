# Tasks：主管可檢視所屬部門的出勤明細

## 1. 抽出共用的範圍解析

- [x] 1.1 新增 `backend/app/services/attendance_scope.py`，提供
      `resolve_visible_user_ids(pool, current_user, user_id, department_id) -> list[int]`：
      admin 不限、manager 限自己部門（未指派部門一律 403、指定他部門成員或他部門 403）、
      其餘角色一律只回自己的 id
- [x] 1.2 `attendance_changes.get_changes()` 改呼叫 1.1，刪除原本內嵌的那段判斷，
      行為必須完全不變

## 2. 後端端點與 service

- [x] 2.1 `routers/attendance.py` 的 `GET /api/attendance` 改掛
      `require_roles("admin", "manager")`，並把 `current_user` 傳進 service
- [x] 2.2 `services/attendance.py` 的 `get_all()` 改成收 `current_user`，
      內部走 `attendance_scope.resolve_visible_user_ids()` 取得 user_ids，
      移除直接用 `department_id` 撈全部成員的既有路徑
- [x] 2.3 檢查 `schemas/attendance.py` 的 `parse_company_attendance_query`，
      確認 `user_id`／`department_id` 仍被解析並原樣交給 service 判斷
      （限縮是 service 的責任，schema 不做授權判斷）

## 2t. 後端測試

- [x] 2t.1 `test_attendance_scope.py`：admin 不限、manager 限自己部門、
      manager 指定他部門成員 403、manager 指定他部門 403、
      **未指派部門的 manager 403**（deny-by-default 的關鍵斷言）、employee 只回自己
- [x] 2t.2 `test_attendance.py`：`GET /api/attendance` 對 employee 回 403、
      對 manager 回 200 且結果不含他部門任何一筆、對 admin 維持原行為
- [x] 2t.3 `test_attendance_changes.py` 既有測試全數維持綠燈（證明 1.2 是純重構）
- [x] 2t.4 同一位 manager 對兩支端點解析出的 user_id 集合一致

## 3. 前端

- [x] 3.1 `AppShell.jsx` 選單該列 `roles` 改 `["admin", "manager"]`，
      label 依角色切換（admin「全公司出勤」／manager「部門出勤」）
- [x] 3.2 `CompanyAttendancePage.jsx` 的 `RoleGate` 改 `["admin", "manager"]`
- [x] 3.3 頁面標題依角色切換；manager 的部門篩選改為唯讀標籤顯示自己的部門名稱，
      員工下拉只列同部門成員，且不送出 `department_id` 以外的部門值
- [x] 3.4 確認 `AttendanceTable` 的 `showUser` 對 manager 仍然顯示姓名欄

## 3t. 前端測試

- [x] 3t.1 `CompanyAttendancePage.test.jsx`：manager 進入時標題為「部門出勤」、
      部門欄位唯讀、admin 進入時維持下拉與「全公司出勤」
- [x] 3t.2 employee 進入時不渲染任何出勤內容
- [x] 3t.3 375px 寬度下篩選區垂直堆疊、無水平捲軸

## 4. e2e

- [x] 4.1 主管視角：登入 → 側邊選單看到「部門出勤」→ 進入頁面 → 表格只出現同部門成員
- [x] 4.2 員工視角：側邊選單無該入口

## 5. 文件

- [x] 5.1 `SPEC.md` §3.1 權限矩陣「上下班打卡」列更正主管欄位，
      並註明與 §4.8 匯出範圍一致
- [x] 5.2 `SPEC.md` 出勤端點章節補上 `GET /api/attendance` 的角色與範圍規則
- [x] 5.3 `docs/UI-SPEC.md` §3.14 與路由表第 11 列更正角色，補上主管的唯讀部門篩選契約
- [x] 5.4 `docs/PITFALLS.md` 新增一則：同一份資料的「匯得出來」與「看得到」走不同的權限
      判斷，容易長期不一致而沒人發現；記錄本次是靠批 B 的權限盤點才被翻出來

## 6. 驗收

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
npx openspec validate fix-manager-attendance-scope --strict
```

三層測試全綠、且以 `manager@demo.com` 實際登入畫面確認看得到部門出勤、看不到他部門資料，
才算完成。
