# 重建執行腳本（RUNBOOK）

**這份是逐批的操作腳本。** 每一批都寫明「要貼什麼指令」「怎麼驗收」「怎麼 commit」「下一步是什麼」。

> **給接手的 AI 開發代理**：如果你是在對話被壓縮後接手的，讀完這份就有完整脈絡，不需要問使用者「我們做到哪了」——看下方的進度追蹤表，第一個沒打勾的就是當前批次。實作前務必先讀 `CLAUDE.md`、`SPEC.md` 對應章節、`docs/PITFALLS.md` 對應章節。

---

## 進度追蹤

每批完成並 commit 後，把該列的 `[ ]` 改成 `[x]`（這是判斷進度的唯一依據）。

- [x] **文件基準點** — 8 份規格文件
- [x] **批 0** — 專案骨架
- [x] **批 1** — 認證與權限
- [x] **批 2** — 打卡與工時計算 ← *建議用 Opus*
- [x] **批 3** — 申請單與審核
- [x] **批 4** — 場地借用
- [x] **批 5** — 管理功能與權限授予 UI
- [x] **批 6** — 匯出報表
- [x] **批 7** — 展示機制
- [ ] **批 8** — 全站響應式 ← *建議用 Opus*
- [ ] **批 9** — 部署上雲

---

## 通用規則（每一批都適用）

**工作目錄**：`C:\Users\Jamie\Desktop\employee-portal-v2`

**使用者的終端機是 Windows PowerShell 5.1**，不支援 `&&`。給使用者手動執行的指令一律用 `;` 串接。

**每批的三個階段**：

1. **實作** — 貼下方對應批次的指令
2. **驗收** — 跑該批的驗收指令，全綠才算完成
3. **commit** — 一批一個 commit，訊息用 `批 N：<批次名稱>`

**每批結束的完整檢查點**（批 0 之後才有意義）：

```powershell
npm run db:reset; npm test; npm run test:e2e
```

**卡住時**：連續兩次修正沒有進展就停下來，先講清楚失敗原因、試過什麼、為什麼沒用，不要繼續盲改。

**對照組**：舊專案完整保留在 `C:\Users\Jamie\Desktop\employee-portal`，行為有疑問時直接去讀它的原始碼比對。它的 397 個後端測試是這次重構的驗收基準，逐批搬過來。

---

## 批 0：專案骨架

**貼這段**：

```
開始批 0：專案骨架。
依據 SPEC.md §5（資料庫模型）與 docs/REBUILD-TASKS.md 批 0，
實作前先讀 docs/PITFALLS.md 的 A 節（資料庫與遷移）。

範圍：
- monorepo 結構（npm workspaces，根目錄統一指令入口）
- docker-compose.yml：兩個 PostgreSQL 16 容器（開發 5432 / 測試 5433）
- db/migrations/001_baseline.sql：12 張表的最終狀態
- db/seed/001_seed.sql + seed 腳本（日期一律相對於 DATE '2026-08-24'）
- backend/app/db_scripts/：migrate / seed / reset 三支 CLI
- 後端骨架：連線池（SSL 自動偵測、NUMERIC 字串 codec）、設定載入、
  錯誤處理 middleware、安全標頭、GET /api/health
- 測試基礎設施：schema 自動重置、_test 資料庫防線、pytest-timeout
- 前端骨架：Vite + React 19 + Tailwind v4（index.css 的 @theme，見 docs/UI-SPEC.md §1）
- .github/workflows/ci.yml
- .env.example、.gitignore

先把 12 張表的 baseline SQL 寫出來給我確認，再往下做其他部分。
```

**驗收**：

```powershell
docker compose up -d
npm install
pip install -r backend/requirements.txt
npm run db:reset
curl http://localhost:3000/api/health
npm run test:backend
```

健康檢查應回 `{"status":"ok","database":"connected",...}`。

**commit**：

```powershell
git add -A; git commit -m "批 0：專案骨架"
```

---

## 批 1：認證與權限

**貼這段**：

```
開始批 1：認證與權限。
依據 SPEC.md §3（角色與權限）§6.1 §6.5、docs/UI-SPEC.md §4，
實作前先讀 docs/PITFALLS.md 的 C 節（權限與安全）。

範圍：
- 登入 / JWT 簽發驗證 / GET /auth/me / 修改密碼（展示帳號密碼鎖定）
- get_current_user()：每請求回 DB 重查，用 LEFT JOIN LATERAL 一併帶出 permissions
- require_roles() 與 require_permission(permission, roles=("admin",))
- db/migrations/002_user_permissions.sql
- GET /users/permissions、PUT /users/{id}/permissions（diff 實作，保留稽核欄位）
- 前端：AuthContext、ProtectedRoute、RoleGate（含 permissions prop）、hasAccess()

重點：權限絕不寫進 JWT；PUT 的服務層要用 DELETE ... <> ALL + INSERT ... ON CONFLICT
DO NOTHING 的 diff 寫法，未變動的權限必須保留原本的 granted_by / granted_at。

測試從舊專案搬：test_auth_login.py、test_auth_change_password.py，
另外新增權限相關測試（見 SPEC.md §8.1 的「細粒度權限」那組）。
```

**驗收**：

```powershell
npm run test:backend; npm run test:frontend
```

必須涵蓋：未帶 token 回 401（不是 403）／同一個舊 token 授權後立即可用、收回後立即被擋／非 admin 打授權端點 403／對 admin 授權回 400／權限整組取代後未變動項目的 `granted_by`、`granted_at` 不變。

**commit**：

```powershell
git add -A; git commit -m "批 1：認證與權限"
```

---

## 批 2：打卡與工時計算 ← 建議切 Opus

**貼這段**：

```
開始批 2：打卡與工時計算。
依據 SPEC.md §4.1（打卡）§4.2（出勤資料純衍生）、docs/UI-SPEC.md §3.4 §3.5，
實作前先讀 docs/PITFALLS.md 的 A2、A3、B1、B2 節。

範圍：
- 上班 / 下班打卡、今日狀態、當日備註
- 純函式：到班偏移量（雙向）、工時起算點、浮動午休、
  正常工時結束（封頂式 vs 累積式取小）、遲到判定、早退判定（零寬限）
- 生效值解析：所有出勤讀取路徑共用同一個函式
- 出勤查詢（個人 / 全公司）與狀態篩選
- 缺勤自動標記排程
- 前端：PunchPanel、TodayStatusCard、AttendanceTable、出勤紀錄頁

這批的驗收規則表在 docs/REBUILD-TASKS.md 批 2，有 10 列邊界案例，
每一列都要有對應測試，而且同一套斷言必須以
08:30–17:30 / 緩衝 15 分 / 午休 12:30–13:30 再跑一次。

測試從舊專案搬：test_attendance_*.py 全部（約 10 個檔案）。
先進計畫模式規劃，我確認後再動手。
```

**驗收**：

```powershell
npm run test:backend
```

驗收規則表 10 列全過 + 非預設設定同樣全過 + `09:10:00`／`09:10:59` 皆判 `normal`、`09:11:00` 判 `late` + `17:59:59` 判早退、`18:00:00` 不判。

**commit**：

```powershell
git add -A; git commit -m "批 2：打卡與工時計算"
```

---

## 批 3：申請單與審核

**貼這段**：

```
開始批 3：申請單與審核。
依據 SPEC.md §4.3（請假）§4.4（加班）§4.5（申請單與審核）§6.3、
docs/UI-SPEC.md §3.7 §3.8 §3.9，實作前先讀 docs/PITFALLS.md 的 C2 節。

範圍：
- 補打卡：同日防重複、不得為未來日期（以虛擬時鐘營業日判斷）
- 請假：逐工作日交集時數、排除週末與國定假日、
  工作時間窗頭尾兩端套用緩衝（中間日不套）、午休固定不浮動
- 加班：30 分鐘單位捨去、扣除午休重疊、起算點防呆、當天有待審申請時阻擋
- 統一審核狀態機、禁止自審（admin 豁免）、部門範圍限制、待審清單
  （admin 的清單要包含自己送出的申請）
- 前端：三個申請表單、我的申請、審核中心

測試從舊專案搬：test_punch_request.py、test_leave_request_hours.py、
test_overtime_request.py、test_overtime_eligibility_guard.py、
test_overtime_min_hours.py、test_request_review_permission.py、
test_punch_request_upsert.py、test_leave_approval_attendance.py
```

**驗收**：

```powershell
npm run test:backend; npm run test:frontend
```

必須涵蓋：manager 審跨部門單 403、審自己的單 403、admin 審自己的單 200／跨週末請假（週五 09:00 → 週一 18:00）時數 16.00／已審核的申請重複審核回 409。

**commit**：

```powershell
git add -A; git commit -m "批 3：申請單與審核"
```

---

## 批 4：場地借用

**貼這段**：

```
開始批 4：場地借用。
依據 SPEC.md §4.6 §6.4、docs/UI-SPEC.md §3.10。

範圍：
- 場地清單、預約建立（應用層預檢 + 資料庫排除約束雙層）、查詢、取消、強制釋放
- 排除約束用半開區間 [)，首尾相接不算衝突
- 錯誤處理器把 23P01 轉譯為 409，衝突訊息要含衝突時段與預約人姓名
- 前端：BookingTimeline（純 CSS 百分比定位，不引圖表函式庫）、
  BookingBlock、預約表單、詳情彈窗

測試從舊專案搬：test_room.py、test_room_booking_overlap.py、
test_room_booking_permission.py、test_room_booking_concurrent.py
```

**驗收**：

```powershell
npm run test:backend; npm run test:frontend
```

必須涵蓋：六種時段重疊拓撲／09:00–11:00 與 11:00–12:00 首尾相接放行／兩筆並行請求搶同一時段只成功一筆且另一筆回 409（不是 500）。

**commit**：

```powershell
git add -A; git commit -m "批 4：場地借用"
```

---

## 批 5：管理功能與權限授予 UI

**貼這段**：

```
開始批 5：管理功能與權限授予 UI。
依據 SPEC.md §4.7（員工與部門）§4.9（國定假日）§6.5 §6.6、
docs/UI-SPEC.md §3.11 ~ §3.16，實作前先讀 docs/PITFALLS.md 的 A2、D1 節。

範圍：
- 員工 CRUD：唯一管理者規則（SINGLE_ADMIN_ONLY / LAST_ADMIN_PROTECTED /
  CANNOT_DELETE_SELF）、員工編號由序列產生、
  extension_number 與 hire_date 未傳時用 COALESCE 保留原值
- 部門 CRUD、國定假日 CRUD、考勤設定、資料庫檢視頁
- 員工資訊頁的「額外權限」欄與授權面板（見 UI-SPEC §3.11）
- 頁面載入用 Promise.allSettled，部門查詢 403 不得拖垮員工清單

測試從舊專案搬：test_user_management.py、test_settings.py、test_holiday.py、
test_admin_schema.py，另外新增 test_partial_update_preserves_extension_number
（PUT /users/{id} 不傳 extension_number 時原值必須保留——舊專案缺這個測試）。
```

**驗收**：

```powershell
npm run test:backend; npm run test:frontend
```

必須涵蓋：`test_partial_update_preserves_extension_number` 通過／employee 進入員工資訊頁不會整頁空白／admin 授予權限後該員工重新整理即看到對應選單。

**commit**：

```powershell
git add -A; git commit -m "批 5：管理功能與權限授予 UI"
```

---

## 批 6：匯出報表

**貼這段**：

```
開始批 6：匯出報表。
依據 SPEC.md §4.8 §6.7、docs/UI-SPEC.md §3.17，
實作前先讀 docs/PITFALLS.md 的 C1、C4 節。

範圍：
- 五種資料類型（employees / attendance / attendance-raw /
  attendance-changes / room-bookings）、欄位勾選、xlsx 產出
- 範圍限縮 deny-by-default：判斷式寫「不是 admin 就限縮部門」，
  絕對不要寫「是 manager 才限縮」；room-bookings 類型除外；
  請求者 department_id 為 NULL 時回 403
- 端點權限寫 require_permission("exports.run", roles=("admin","manager"))，
  roles 參數絕對不能省略，省略會砍掉現有 manager 的匯出權
- 前端：受限縮者不顯示部門篩選、員工下拉只列自己部門、
  提示文案不得寫「主管身分」（被授權的可能是一般員工）

測試從舊專案搬：test_export.py，另外新增匯出範圍越權的迴歸測試。
```

**驗收**：

```powershell
npm run test:backend; npm run test:frontend
```

必須涵蓋：被授予 `exports.run` 的員工帶別部門的 `department_id` 仍只拿到自己部門資料／指定他部門成員的 `user_id` 回 403／`department_id` 為 NULL 者回 403／**manager 既有的匯出權不受影響**。

**commit**：

```powershell
git add -A; git commit -m "批 6：匯出報表"
```

---

## 批 7：展示機制

**貼這段**：

```
開始批 7：展示機制。
依據 SPEC.md §4.10（虛擬時鐘）§4.11（展示資料重置）§6.7、
實作前先讀 docs/PITFALLS.md 的 B3、B4、E 節（全節）。

範圍：
- 虛擬時鐘：後端 clamp（2026-08-24 ~ 08-31）、
  前端每秒本地推算 + 60 秒向後端校正
- 展示資料一鍵重置（admin）、閒置自動重置排程
  （計時器刻意用真實時間 time.monotonic()，不用虛擬時鐘）
- 種子資料：業務時刻一律用佔位符，由 seed 腳本呼叫正式業務函式算出後代入；
  所有日期相對於 DATE '2026-08-24' 推算，不用 CURRENT_DATE
- 種子資料全表掃描驗證測試

測試從舊專案搬：test_clock.py、test_demo_reset.py、
test_seed_data_consistency.py、test_seed_business_rules.py、
test_absent_auto_mark.py
```

**驗收**：

```powershell
npm run db:reset; npm run test:backend; npm run test:frontend
```

必須涵蓋：`test_seed_business_rules.py` 全表掃描全綠／重置後種子加班申請的起始時間皆 ≥ 該日可認列起算點／畫面上停留 1 分鐘不動，標頭時鐘持續走動且與隨後的打卡時間一致。

**commit**：

```powershell
git add -A; git commit -m "批 7：展示機制"
```

---

## 批 8：全站響應式 ← 建議切 Opus

**貼這段**：

```
開始批 8：全站響應式適配。
依據 docs/UI-SPEC.md §2（響應式斷點規範）全節。

範圍：
- 版面骨架：手機改抽屜式側邊欄 + 漢堡按鈕（這是核心，桌機版行為不得改變）
- 標頭元素在手機換行或收進抽屜
- 8 張寬表格改卡片式：用 lg:hidden / hidden lg:block 雙結構，
  不要用 JS 判斷視窗寬度
- 時間軸維持水平捲動 + 加捲動提示 + 加大色塊
- TodayStatusCard、表單 grid 手機單欄
- 四個對話框手機接近全螢幕、內容可捲動
- 觸控目標最小 44×44px

驗收基準寬度 375px，任何頁面都不得出現整頁水平捲軸
（表格 / 時間軸容器內部的水平捲動是允許的）。
補一組 Playwright 以 375×812 視窗跑主要頁面的測試。
先進計畫模式規劃，我確認後再動手。
```

**驗收**：

```powershell
npm run test:frontend; npm run db:reset; npm run test:e2e
```

再手動用瀏覽器縮到 375px 走一遍：登入 → 打卡 → 看出勤 → 送補打卡申請。**桌機版視覺與行為必須完全不變**（回歸點）。

**commit**：

```powershell
git add -A; git commit -m "批 8：全站響應式適配"
```

---

## 批 9：部署上雲

**貼這段**：

```
開始批 9：部署上雲。
依據 README.md 的「雲端部署」章節、docs/PITFALLS.md 的 G 節。

先做本機端能做的部分：
- 確認 render.yaml、frontend/vercel.json、.env.example 齊全
- 產生一組 JWT_SECRET 給我
- 把完整的部署步驟整理成待辦清單，標明哪幾步需要我自己在瀏覽器操作

需要我操作的部分（帳號登入類）你不用做，列給我照做即可。
```

**接著的順序**（帳號操作由使用者本人執行）：

1. **GitHub**
   ```powershell
   gh auth refresh -h github.com -s workflow
   gh repo create employee-portal-v2 --public --source=. --remote=origin --push
   ```
   （`workflow` scope 一定要先補，否則含 `.github/workflows/` 的 push 會被拒絕）

2. **Neon**：建立新專案，**地區選美國東部**（與 Render 同區，跨區會讓每次查詢多付數百毫秒），取得 pooled connection string，貼回對話讓 AI 執行：
   ```powershell
   $env:DATABASE_URL="<neon 連線字串>"; npm run db:migrate; npm run db:seed
   ```

3. **Render**：New → Blueprint → 選 repo，填 `DATABASE_URL`、`JWT_SECRET`、`CORS_ORIGINS`（先填 `http://localhost:5173` 佔位）、`SMTP_*` 留空。等建置完成後記下服務網址。

4. **Vercel**：Add New → Project → 選同一個 repo，**Root Directory 改成 `frontend`**（不改會被誤判成多服務專案），Build Command 的 Override **關掉**，環境變數 `VITE_API_BASE_URL` = `https://<render 網址>/api`。

5. **回 Render** 把 `CORS_ORIGINS` 改成 Vercel 正式網址（不要有結尾斜線），存檔自動重新部署。

6. **驗證**：
   ```powershell
   curl https://<render 網址>/api/health
   ```
   應回 `"database":"connected"`。再用展示帳號在線上走一遍登入 → 打卡 → 送申請 → 審核，並用手機開一次。

**commit**：

```powershell
git add -A; git commit -m "批 9：部署設定"
```

---

## 全部完成後的等價性驗證

1. **397 個移植過來的後端測試全綠**——最硬的證據。
2. **新舊兩站同時開著逐一比對**：同一組展示帳號、同一個虛擬時鐘時間點，走一遍八個情境（打卡 → 補打卡 → 審核 → 請假 → 加班 → 場地預約 → 匯出 → 展示重置），畫面與數字要一致。
3. **手機視窗（375px）走一遍員工日常情境**。
4. `git log` 應該是乾淨的十筆，沒有「修正上一個 commit 的錯」這種紀錄。
