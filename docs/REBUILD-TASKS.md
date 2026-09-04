# 重建任務清單與操作手冊

本文件是**實際照著做的那一份**。分兩部分：前半是操作流程，後半是十批的任務與驗收條件。

---

## 第一部分：操作流程

### 0. 前置準備（只做一次）

```powershell
cd C:\Users\Jamie\Desktop\employee-portal-v2; git init; git branch -M main
```

> Windows PowerShell 5.1 不支援 `&&` 串接，一律用 `;`。

確認以下文件都在（規格已備妥，這是重建的依據）：

```
employee-portal-v2/
├── CLAUDE.md              ← 專案守則，開發代理必須讀到這一份
├── SPEC.md                ← 系統規格
├── README.md              ← 開發者文件
├── docs/
│   ├── UI-SPEC.md         ← 介面規格（含響應式）
│   ├── PITFALLS.md        ← 踩坑紀錄
│   ├── USER_GUIDE.md      ← 使用手冊
│   └── REBUILD-TASKS.md   ← 本檔
└── openspec/
    └── config.yaml        ← 專案慣例（重建期間不跑 OpenSpec 流程，見下方說明）
```

**工作目錄必須設在 `employee-portal-v2`**，否則 `CLAUDE.md` 不會被載入，開發代理會少掉整份專案守則。

### 1. 關於 OpenSpec

**重建期間不使用 OpenSpec 流程。** 理由：OpenSpec 的價值在「從模糊需求推導出規格」，但這次的規格已經完整寫在 `SPEC.md` 與 `docs/UI-SPEC.md` 裡，再跑一次 propose → design → tasks 等於把寫好的東西重新推導一遍。

`openspec/` 目錄仍保留——**重建完成後**要加新功能時（需求是模糊的），那時候才是它派上用場的時機。

### 2. 每一批的標準循環

以「批 2：打卡與工時計算」為例。

**步驟 A — 下達批次指令**

```
開始批 2：打卡與工時計算。
依據 SPEC.md §4.1 §4.2、docs/UI-SPEC.md §3.4 §3.5，
實作前先讀 docs/PITFALLS.md 的 A、B 兩節，
範圍與驗收規則表見 docs/REBUILD-TASKS.md 批 2。
```

複雜的批次（批 2、批 8）建議先進入計畫模式（連按兩下 `Shift+Tab`），讓它先提實作計畫給你確認再動手。

**步驟 B — 實作與逐段驗證**

實作過程中每完成一個功能群組就跑對應測試，不要整批寫完才第一次跑。中途方向不對就直接打斷說明，不用等它做完。

**步驟 C — 完整檢查點**

```powershell
npm run db:reset; npm test; npm run test:e2e
```

全綠才進下一批。**不要累積技術債往下衝**——這次重構的整個意義就是不留爛攤子。

**步驟 D — commit**

```powershell
git add -A; git commit -m "批 2：打卡與工時計算"
```

一批一個 commit，最後 `git log` 應該是乾淨的十筆，沒有「修正上一個 commit 的錯」這種紀錄。

### 3. 幾個實用技巧

**善用對照組**：舊專案還在 `C:\Users\Jamie\Desktop\employee-portal`，行為有疑問時直接叫它去比對：

```
舊專案在 C:\Users\Jamie\Desktop\employee-portal，去看 backend/app/services/attendance.py
的 compute_normal_work_end 是怎麼處理封頂式與累積式的，確認我們的實作語意一致
```

**測試移植**：舊專案的 397 個測試是這次重構最重要的驗收基準，逐批搬：

```
把舊專案 backend/tests/test_attendance_arrival_delay.py、test_attendance_flex_lunch.py、
test_attendance_late_boundary.py 搬過來，路徑與 import 依新專案結構調整，跑起來確認全綠
```

**模型選擇**：批 0、批 3~7 多半是照規格寫 CRUD 與 UI，規格夠細；**批 2（工時演算法）與批 8（響應式）建議用能力較強的模型**——批 2 的驗收規則表有 10 列邊界案例，錯一個符號整批數字就跑掉。

**卡住的時候**：連續兩次修正沒有進展就停下來，先問清楚現況：

```
先不要改程式碼。跟我說明現在的失敗原因是什麼、你試過什麼、為什麼沒用
```

### 3. 常見狀況

| 狀況 | 處理 |
| :--- | :--- |
| 測試卡住不動超過兩分鐘 | 確認 Docker Desktop 有開（`docker ps`）。後端測試需要本機 PostgreSQL 容器 |
| e2e 測試失敗但本機手動操作正常 | 先 `npm run db:reset`。e2e 打的是開發資料庫，會撞到上一次跑測試留下的資料 |
| 改了後端程式碼但行為沒變 | 重啟後端 dev server，`--reload` 在此環境不可靠 |
| 它想建立 `tailwind.config.js` | 阻止它。Tailwind v4 是 CSS-first，會靜默忽略該檔（見 PITFALLS D4） |
| 它把時間寫死成 `09:00` | 阻止它。一律讀 `system_settings`（見 CLAUDE.md 硬性規則） |
| 它想用 mock 資料庫寫後端測試 | 阻止它。本專案的風險就在 SQL 語意本身 |

---

## 第二部分：十批任務

每批都是「資料庫 + 後端 + 前端 + 測試」的完整垂直切片。

### 批 0：專案骨架

**範圍**
- monorepo 結構（npm workspaces，根目錄統一指令入口）
- `docker-compose.yml`：兩個 PostgreSQL 16 容器（開發 5432 / 測試 5433）
- `db/migrations/001_baseline.sql`：11 張表的最終狀態（見 SPEC.md §5）
- `db/seed/001_seed.sql` + seed 腳本（日期一律相對於 `DATE '2026-08-24'`）
- `db_scripts/`：migrate / seed / reset 三支 CLI
- 後端骨架：連線池（含 SSL 自動偵測、NUMERIC 字串 codec）、設定載入、錯誤處理 middleware、安全標頭、`GET /api/health`
- 測試基礎設施：schema 自動重置、`_test` 資料庫防線、`pytest-timeout`
- 前端骨架：Vite + React 19 + Tailwind v4（`index.css` 的 `@theme`）
- `.github/workflows/ci.yml`

**必讀**：PITFALLS A1、A4、A5、A6

**驗收**
```bash
docker compose up -d
npm install && pip install -r backend/requirements.txt
npm run db:reset
curl http://localhost:3000/api/health   # 應回 {"status":"ok","database":"connected",...}
npm run test:backend                     # 骨架測試（health、schema）全綠
```

### 批 1：認證與權限

**範圍**
- 登入／JWT 簽發驗證／`GET /auth/me`／修改密碼（展示帳號鎖定）
- `get_current_user()`：**每請求回 DB 重查**，用 `LEFT JOIN LATERAL` 一併帶出 `permissions`
- `require_roles()` 與 `require_permission(permission, roles=("admin",))`
- `db/migrations/002_user_permissions.sql`
- 授權 API：`GET /users/permissions`、`PUT /users/{id}/permissions`（diff 實作，保留稽核）
- 前端：`AuthContext`、`ProtectedRoute`、`RoleGate`（含 `permissions` prop）、`hasAccess()`

**必讀**：PITFALLS C1–C6

**驗收**
- 未帶 token 回 401（不是 403）
- 同一個舊 token：授權後立即可用、收回後立即被擋
- 非 admin 打授權端點 403；對 admin 授權回 400
- 權限整組取代後，未變動項目的 `granted_by`／`granted_at` 不變

### 批 2：打卡與工時計算

**範圍**
- 上班／下班打卡、今日狀態、當日備註
- 純函式：到班偏移量（雙向）、工時起算點、浮動午休、正常工時結束（封頂式 vs 累積式取小）、遲到判定、早退判定（零寬限）
- 生效值解析（`attendance_effective`）：所有出勤讀取路徑共用
- 出勤查詢（個人／全公司）與狀態篩選
- 缺勤自動標記排程
- 前端：`PunchPanel`、`TodayStatusCard`、`AttendanceTable`、出勤紀錄頁

**必讀**：PITFALLS A2、A3、B1、B2、F1

**驗收規則表**（設定：09:00–18:00、午休 12:00–13:00、緩衝 10 分）

| 打卡 in / out | 偏移量 | 工時起算 | 浮動午休 | 正常工時結束 | work_hours |
|---|---|---|---|---|---|
| 09:05 / 18:10 | +5 | 09:05 | 12:05–13:05 | 18:05 | 8.00 |
| 09:23 / 18:23 | +10（上限） | 09:23 | 12:10–13:10 | 18:10 | 7.78 |
| 09:10 / 13:10 | +10 | 09:10 | 12:10–13:10 | 18:10 | 3.00 |
| 08:48 / 12:48 | −10（下限） | 08:50 | 11:50–12:50 | 17:50 | 3.00 |
| 08:55 / 12:55 | −5 | 08:55 | 11:55–12:55 | 17:55 | 3.00 |
| 無假 12:02 / 18:06 | 0（錨點 13:00，不給負向） | 12:02 | 12:00–13:00 | 18:00 | 5.00 |
| 無假 13:08 / 18:08 | +8 | 13:08 | 12:08–13:08 | 18:08 | 5.00 |
| 無假 13:20 / 18:20 | +10 | 13:20 | 12:10–13:10 | 18:10 | 4.83 |
| 上午請假 09–12，12:02 / 18:00 | 0 | 13:00 | 12:00–13:00 | 18:00 | 5.00 |
| 下午請假 13–18，09:02 / 12:02 | +2 | 09:02 | 12:02–13:02 | 12:02（累積式勝出） | 3.00、**非早退** |

外加：`09:10:00` 與 `09:10:59` 皆判 `normal`、`09:11:00` 判 `late`；`17:59:59` 下班判早退、`18:00:00` 不判。
**同一套斷言必須以 08:30–17:30／緩衝 15／午休 12:30–13:30 再跑一次。**

> 上午請假那一列的「工時起算」是 **13:00** 不是打卡時間 12:02：該日請假到 12:00，
> 應到班時間依規則會被推到午休結束 13:00，`工時起算 = max(12:02, 13:00)`。
> 兩種算法的 `work_hours` 都是 5.00（差額被午休吸收），但實作要以 13:00 為準。
> 兩組設定的完整期望值見 `backend/tests/test_work_hours.py`。

### 批 3：申請單與審核

**範圍**
- 三種申請單的建立與驗證（補打卡防重複、不得未來日期；請假時數逐工作日交集＋頭尾緩衝窗；加班 30 分鐘單位、扣午休、起算點防呆、待審阻擋）
- 統一審核狀態機、禁止自審（admin 豁免）、部門範圍限制、待審清單
- 前端：三個申請表單、我的申請、審核中心

**必讀**：PITFALLS C2

**驗收**
- manager 審跨部門單 403、審自己的單 403；admin 審自己的單 200
- admin 的待審清單**包含**自己送出的申請
- 跨週末請假（週五 09:00 → 週一 18:00）時數為 16.00，不是把週末算進去
- 已審核的申請重複審核回 409

### 批 4：場地借用

**範圍**
- 場地清單、預約建立（應用層預檢 + DB 排除約束）、查詢、取消、強制釋放
- 前端：時間軸、預約表單、詳情彈窗

**驗收**
- 六種時段重疊拓撲皆正確判定
- 09:00–11:00 與 11:00–12:00 **首尾相接放行**
- 兩筆並行請求搶同一時段，**只有一筆成功**，另一筆回 409（不是 500）

### 批 5：管理功能與權限授予 UI

**範圍**
- 員工 CRUD（唯一管理者規則、員工編號序列、`COALESCE` 保留）
- 部門 CRUD、國定假日 CRUD、考勤設定、資料庫檢視頁
- **員工資訊頁的額外權限欄與授權面板**（見 UI-SPEC §3.11）

**必讀**：PITFALLS A2、D1

**驗收**
- `SINGLE_ADMIN_ONLY`、`LAST_ADMIN_PROTECTED`、`CANNOT_DELETE_SELF`
- **`test_partial_update_preserves_extension_number`**：`PUT /users/{id}` 不傳 `extension_number` 時原值必須保留
- employee 進入員工資訊頁不會因為 `GET /departments` 回 403 而整頁空白
- admin 授予權限後，該員工重新整理即看到對應選單

### 批 6：匯出報表

**範圍**
- 五種資料類型、欄位勾選、xlsx 產出
- **範圍限縮 deny-by-default**（非 admin 一律限縮部門）

**必讀**：PITFALLS C1、C4

**驗收**
- 被授予 `exports.run` 的員工，帶 `department_id=別的部門` 仍只拿得到自己部門的資料
- 指定他部門成員的 `user_id` 回 403
- `department_id` 為 NULL 者回 403（不得被當成不限部門）
- **manager 的既有匯出權不受影響**（迴歸點）

### 批 7：展示機制

**範圍**
- 虛擬時鐘（後端 clamp + 前端每秒推算 / 60 秒校正）
- 展示資料一鍵重置、閒置自動重置排程（**用真實時間計時**）
- 種子資料（佔位符由業務函式算出）+ 全表掃描驗證測試

**必讀**：PITFALLS B3、B4、E1、E2、E3

**驗收**
- 停留 1 分鐘不動，標頭時鐘持續走動，且與隨後的打卡時間一致
- `test_seed_business_rules.py` 全表掃描全綠
- 重置後種子資料的加班申請起始時間皆 ≥ 該日的可認列起算點

### 批 8：全站響應式適配

**範圍**（見 UI-SPEC §2）
- 版面骨架：手機抽屜式側邊欄 + 漢堡按鈕（**這是核心**）
- 標頭元素換行／收納
- 8 張寬表格改卡片式（`lg:hidden` / `hidden lg:block` 雙結構）
- 時間軸維持水平捲動 + 捲動提示 + 加大色塊
- 今日狀態卡、表單 grid 手機單欄
- 四個對話框手機接近全螢幕
- 觸控目標 ≥ 44px

**驗收**
- Playwright 以 375×812 視窗跑一遍主要頁面，**不得出現整頁水平捲軸**
- 手機視窗走完員工日常情境：登入 → 打卡 → 看出勤 → 送補打卡申請
- 桌機版視覺與行為**完全不變**（回歸點）

### 批 9：部署上雲

**範圍**：見 README.md 的部署 runbook。

1. GitHub：`gh repo create employee-portal-v2 --public --source=. --remote=origin --push`
2. Neon：新開專案（**選美國東部，與 Render 同區**），取得 pooled connection string
3. 本機對新庫執行一次 `DATABASE_URL="..." npm run db:migrate && DATABASE_URL="..." npm run db:seed`
4. Render：Blueprint 匯入，填 `DATABASE_URL`／`JWT_SECRET`／`CORS_ORIGINS`（先填佔位）
5. Vercel：匯入，**Root Directory 設為 `frontend`**，環境變數 `VITE_API_BASE_URL` = Render 網址 + `/api`
6. 回 Render 把 `CORS_ORIGINS` 改成 Vercel 正式網址

**必讀**：PITFALLS G1–G6

**驗收**
- `curl https://<render>/api/health` 回 `database: connected`
- 線上用展示帳號登入、打卡、送申請、審核走一遍
- 手機開實際網址走一遍

---

## 第三部分：完成後的等價性驗證

重構「成功」的定義：

1. **397 個移植過來的後端測試全綠**。這是最硬的證據——這些測試斷言的是精確到小數點兩位的工時、精確到分鐘的邊界判定、精確的錯誤碼與中文訊息。
2. **新舊兩站同時開著逐一比對**：用同一組展示帳號、同一個虛擬時鐘時間點，走一遍八個情境（打卡 → 補打卡 → 審核 → 請假 → 加班 → 場地預約 → 匯出 → 展示重置），畫面與數字要一致。
3. **手機視窗（375px）走一遍員工日常情境**。
4. 新專案的 `git log` 乾淨：十個批次、每批一個 commit，沒有「修正上一個 commit 的錯」這種紀錄。
