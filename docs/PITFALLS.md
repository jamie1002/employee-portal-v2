# 踩坑紀錄

前一版開發過程中**實測才發現**的問題。這些在規格上看不出來，但重寫時極容易再踩一次。實作對應功能前請先看過該區塊。

格式：**症狀 → 根因 → 修法**。

---

## A. 資料庫與遷移

### A1. 獨立重跑 pytest 會整批報錯或整個卡死

**症狀**：`pytest` 以獨立 process 執行（例如只想重跑某幾個測試檔）時，輸出一長串 `E`（幾乎每個用到 `client` fixture 的測試都報錯），或整個 process 卡住不動，連線池全部停在 idle。

**根因**：測試 helper 用 **process-local** 旗標判斷是否需要重跑 migration，每次啟動新 process 這個旗標都是 `False`，於是把所有 `.sql` 重跑一次。當時 `002` 會把 `attendances_status_check` 收窄，而 `004` 才放寬加入 `'on_leave'`——如果測試資料庫裡有**前一次** pytest 留下的 `status='on_leave'` 資料列，重跑 `002` 就會違反既有資料拋 `CheckViolationError`，且發生在幾乎每個測試共用的 fixture 裡。

**修法**：測試 helper 在套用 migration 之前自己執行 `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`，保證每個 pytest process 都從空 schema 開始。**執行 DROP 前必須再驗證一次資料庫名稱以 `_test` 結尾**——這是把整個 schema 砍掉的操作，防線要貼著危險動作寫，不能只靠模組載入時那一次檢查。

**這一版的預防**：遷移檔已壓平成 `001_baseline.sql`，不存在「先收窄後放寬」的順序衝突。但 schema 自動重置的機制仍要保留，且**不得**改回「靠人記得先手動清空」——正確性繫於有沒有人記得執行額外步驟，本身就是問題。

另外加上 `pytest-timeout`（`timeout = 120`）：任何測試若因未知原因卡住，會在 2 分鐘內以帶 traceback 的逾時失敗收場，不會無限等待。

### A2. UPSERT 漏寫 COALESCE 造成靜默資料遺失

**症狀**：員工只送出「補上班卡」的申請並核准後，該日的**下班時間被清成 NULL**。API 沒有報錯，資料悄悄不見。

**根因**：`ON CONFLICT DO UPDATE SET punch_out_time = $5` 直接覆蓋，而 `type='in'` 的請求根本沒傳 `$5`（是 NULL）。

**修法**：所有 UPSERT 的更新分支，未提供的欄位一律寫成 `COALESCE($n, 欄位名)`。同樣的規則適用於 `PUT /users/{id}` 的 `extension_number`／`hire_date`。

> **這比回 500 更難察覺**——500 會有人回報，靜默資料遺失要等到有人發現自己的出勤紀錄不見才會知道。必須有測試釘住「不傳的欄位保留原值」，光測「有傳值時會存進去」抓不到這個回歸。

### A3. `updated_at` 觸發器與虛擬時鐘互相矛盾

**症狀**：把虛擬時鐘調到 8/25 打卡後，該列的 `punch_in_time` 是 8/25，但 `updated_at` 是真實的今天。

**根因**：資料庫觸發器內部呼叫 SQL 的 `now()`，它不知道虛擬時鐘的偏移量。

**修法**：`attendances` **不掛** `updated_at` 觸發器，時間一律由應用層帶入 `get_virtual_now()` 算出的值再寫入。其他不受虛擬時鐘影響的表（departments／users／system_settings／room_bookings）維持觸發器。

### A4. 每支 migration 都會重跑

這個專案**沒有 `schema_migrations` 版本表**，`npm run db:migrate` 每次都會把 `db/migrations/*.sql` 全部重跑一遍。所以每支檔案都必須自行保證可重複執行。

- 表：`CREATE TABLE IF NOT EXISTS`
- 欄位：`ADD COLUMN IF NOT EXISTS`
- 資料：`ON CONFLICT DO NOTHING`
- **CHECK 約束：必須用「先 `DROP CONSTRAINT IF EXISTS` 再 `ADD CONSTRAINT`」**，不能寫在 `CREATE TABLE IF NOT EXISTS` 裡面——表已存在時整段會被跳過，日後要改白名單改這支檔案不會生效。

### A5. asyncpg 的型別邊界

**症狀**：查詢拋出型別錯誤，訊息指向某個日期參數。

**根因**：asyncpg 對 `DATE`／`TIME`／`TIMESTAMPTZ` 欄位的查詢參數**要求原生 Python 物件**（`datetime.date`／`time`／`datetime`），傳字串不會自動轉。

**修法**：集中在 `app/utils/pg_types.py` 處理（`pg_date()` 等），所有 repository 一律走它。

### A6. NUMERIC 必須解碼成字串

**症狀**：工時顯示成 `8` 而不是 `8.00`，測試斷言 `== "8.00"` 全部失敗。

**根因**：asyncpg 預設把 `NUMERIC` 解成 `Decimal`，與前一版（Node 的 `pg` 驅動）預設回傳固定小數位字串的行為不同。

**修法**：在連線池的 `init` 回呼註冊 `numeric` 的 type codec，編碼與解碼都用 `str`。前端顯示格式與所有測試斷言都依賴 `"8.00"` 這個格式，不要改成 float。

### A7. 「先查、有列就 UPDATE、沒有就 INSERT」不是原子操作，並行時會讓 UNIQUE 防線失效

**症狀**：CI 間歇性出現 `test_concurrent_punch_in_exactly_one_succeeds` 失敗，`assert sorted([first.status_code, second.status_code]) == [201, 409]` 拿到 `[201, 201]`——兩個並行的上班打卡都「成功」了，本機單獨重跑幾乎必過，很容易被誤判成單純的 CI 環境雜訊。

**根因**：`upsert_attendance()` 原本的寫法是「先 `SELECT` 有沒有既有列、有就 `UPDATE`、沒有就 `INSERT`」，這個決策橫跨兩個獨立的資料庫陳述式，中間隔著一段 `await`。兩個並行的上班打卡各自的 `SELECT` 都可能先看到「沒有列」而決定要 `INSERT`；但真正執行到那個 `INSERT` 時，其中一個請求所在的交易已經因為另一個先提交而看到「有列了」，於是它會**再查一次並改口走 `UPDATE` 分支**（這是 `upsert_attendance()` 自己的邏輯，不是資料庫幫你做的），安靜地把對方剛寫入的資料覆蓋成幾乎相同的值——`UNIQUE(user_id, punch_date)` 這道防線因此完全沒被踩到，兩邊都以為自己合法地建立或更新了一筆紀錄。這跟 E6 是同一類「共用可變狀態 + 非原子的檢查再行動」問題，只是這次共用狀態是資料庫的一列，不是 e2e 的種子資料。

**修法**：不要用「查了再決定要 INSERT 還是 UPDATE」這種橫跨兩個陳述式的邏輯保護並行安全，改用單一陳述式的 `INSERT ... ON CONFLICT (user_id, punch_date) DO UPDATE ... WHERE <欄位> IS NULL RETURNING ...`——PostgreSQL 保證同一時間只有一個交易能通過 `WHERE` guard，另一個會因為 `RETURNING` 不到列而明確知道自己輸了race，由呼叫端據此回報 409，而不是誤判成功。`upsert_attendance()` 加了 `require_field_null` 參數做這件事，`punch_in()`／`punch_out()` 都改用它；不需要並行安全的呼叫端（種子腳本）維持原本的一般 upsert 語意不受影響。

**驗收方式**：光靠「重跑幾次沒再失敗」不能證明修好了，因為原本的 bug 本來就不是每次都觸發——本機用迴圈連續重跑該測試十幾次確認穩定全綠，且要理解成因（追蹤兩個陳述式之間的競態視窗），而不是只看到「這次綠了」就結案。

---

## B. 時區與時間

### B1. 用 UTC 日期會把早班打卡記到前一天

**症狀**：台灣時間 08:00 的打卡，`punch_date` 被記成前一天。

**根因**：直接用 UTC 日期推導「今天」。台灣時間 08:00 對應 UTC 前一日 00:00。

**修法**：所有「今天是哪一天」的判斷一律 `get_business_date(moment, tz='Asia/Taipei')`。這個錯誤會沿著 `UNIQUE(user_id, punch_date)` 一路污染補打卡的 UPSERT 目標列，屬於難以察覺的連鎖錯誤。

### B2. 判定粒度混用秒與分鐘

**症狀**：同一個「9 點 10 分」，打 `09:10:00` 判正常、打 `09:10:40` 判遲到。假日 `08:56:37` 打卡後申請 `08:56` 開始的加班，被自己的防呆擋下並顯示「加班最早可從 08:56 開始申請」這種自相矛盾的訊息。

**根因**：部分路徑比對到秒，部分截斷到分鐘。

**修法**：**所有時間規則的比較一律先截斷到分鐘**（`replace(second=0, microsecond=0)`），在每個接受時間參數的純函式**入口**就截斷，不依賴呼叫端記得先處理。

### B3. 展示時鐘顯示凍結

**症狀**：登入時標頭顯示 09:08，停留幾分鐘後打卡，紀錄卻是 09:12。

**根因**：前端只在元件掛載時取一次 `GET /demo/clock`，但後端的虛擬時鐘是「虛擬錨點 + 真實流逝時間」，會持續走動。**顯示是死的，打卡是活的。**

**修法**：前端每秒依上次校正的偏移量本地推算，每 60 秒重新呼叫 API 校正（涵蓋別人調整時鐘的情況）。

### B4. 閒置自動重置不能用虛擬時鐘

**症狀**（設計時就避開了，但很容易寫錯）：若閒置計時器改用虛擬時間，虛擬時間到達 clamp 上限後就不再前進，重置機制會**永遠不觸發**。

**修法**：閒置計時器刻意使用真實時間（`time.monotonic()`）。這是虛擬時鐘規則的**唯一例外**，要在註解裡寫明理由。

### B5. e2e 測試用真實時鐘算日期，遲早整批壞掉

**症狀**：CI 與本機的補打卡 e2e 測試突然開始穩定失敗，畫面停在表單頁不導頁；錯誤訊息其實是「補打卡日期不得為未來日期」。

**根因**：測試用 `new Date()`（真實系統時間）算「最近一個工作日」當補打卡目標日期，但系統的「今天」是固定鎖在 `2026-08-24` 的虛擬時鐘。真實日期持續往前走、超過這個錨點後，算出的目標日期就變成「相對於虛擬時鐘的未來」，被後端的未來日期防呆正常擋下。**這不是程式壞掉，是測試自己的假設從一開始就跟系統設計矛盾，只是延遲發作。**

**修法**：e2e 的日期一律以虛擬時鐘的固定錨點（`new Date(2026, 7, 24)`）往前推算，**禁止在測試中出現 `new Date()`**。

> **除錯過程的教訓**：這個問題一開始被誤判為「剛做完的效能優化拖慢了回應」。是用 `git checkout` 把相關程式碼**退回舊版重測、問題依然存在**，才排除了那個嫌疑。症狀相似不代表根因相同——**先做對照實驗再下結論**。

---

## C. 權限與安全

### C1. 「不是 manager 就是全公司」的 deny-by-default 反例

**症狀**（v1.3 的實際漏洞）：`department_id` 為 NULL 的 manager 匯出時，NULL 被當成「不限部門」而放行成全公司範圍。

**根因**：範圍限縮寫成「**是 manager 才限縮**」，等價於「不是 manager 就是全公司」。這在只有三種角色時碰巧是對的，但一旦出現第四種可匯出的身分（例如被授予 `exports.run` 的一般員工），就會直接落進不限縮分支。

**修法**：反轉成「**不是 admin 就限縮**」，並在請求者 `department_id` 為 NULL 時直接回 403 而非放行。未來再新增任何可匯出身分，預設都是部門範圍，要放寬必須明確寫在判斷函式裡。

### C2. admin 自審豁免若沒配套就是死 code

**症狀**：admin 送出的申請永遠看不到、也永遠審不了。

**根因**：待審清單查詢一律排除「自己送出的申請」，但 admin 又被豁免禁止自審——豁免規則永遠不會被觸發。

**修法**：待審清單對 `admin` 呼叫時**包含**自己送出的申請，對 `manager` 才排除。

### C3. 權限寫進 JWT 就無法即時收回

**修法**：權限（與 role、department_id）一律**每個請求回資料庫重查**，token payload 內的值不被信任。`get_current_user()` 本來就要查一次使用者，權限用 `LEFT JOIN LATERAL` 跟著同一次查詢帶出，**不增加往返**。

必須用測試釘死：**同一個舊 token**，授權後立即可用、收回後立即被擋。否則日後有人為了「省一次查詢」把權限塞進 token，收回就不會即時生效。

### C4. 前端的權限守門不是安全邊界

`RoleGate` 與選單過濾只影響畫面，完全不影響後端。**每一支端點都必須自己掛權限 dependency。**

特別注意匯出端點是唯一「角色 ＋ 權限」並存的，寫成 `require_permission("exports.run")` 會套用預設 `roles=("admin",)`，**直接砍掉現有 manager 的匯出權**。必須寫 `roles=("admin","manager")`。

### C5. 權限「刪光重建」會洗掉稽核紀錄

**症狀**：畫面上顯示的「由 XXX 於 X/X 授予」永遠是最後一次按儲存的時間。

**根因**：`PUT` 整組取代時，服務層圖方便寫成「先刪光該使用者的全部權限、再全部插入」。

**修法**：API 語意維持整組取代（前端不必算差集），但服務層用 diff 實作：

```sql
DELETE FROM user_permissions WHERE user_id = $1 AND permission <> ALL($2::text[]);
INSERT INTO user_permissions (user_id, permission, granted_by)
SELECT $1, p, $3 FROM unnest($2::text[]) AS p
ON CONFLICT (user_id, permission) DO NOTHING;
```

未變動的權限靠 `DO NOTHING` 原封不動保留原本的授權人與時間。要有測試釘住這件事。

### C6. `granted_by` 可能是 NULL

授權人被刪除時 `granted_by` 轉 NULL（刻意保留稽核列）。前端每一處顯示都要有 fallback，否則會出現「由  於 8/17 授予」這種破碎文案。

---

## D. 前端

### D1. `Promise.all` 整包 reject 導致頁面空白

**症狀**：一般員工登入後「員工資訊」頁完全空白，且沒有任何錯誤訊息。

**根因**：頁面用 `Promise.all([getUsers(), getDepartments()])` 一次載入，但 `GET /departments` 對 employee 回 403，整包 reject 導致 users 永遠是空陣列且靜默失敗。**根因不是 RBAC 設定錯誤，是前端的錯誤處理方式。**

**修法**：改用 `Promise.allSettled`，只有真正必要的那支失敗才顯示整頁錯誤；輔助資料失敗就降級（例如 employee 改從已載入的 users 陣列推導部門選項），**不為了輔助功能去放寬 API 權限**。

### D2. 依 useEffect 相依項放會走動的時間物件

**症狀**（實作時發現並避開）：把每秒更新的虛擬時鐘 Date 物件直接放進資料載入 `useEffect` 的相依陣列，會變成每秒打 4 次 API。

**修法**：先把時間衍生成穩定的字串（`startDate`／`endDate`），相依項放字串。

### D3. Markdown 渲染器把每一行都當成獨立段落

**症狀**：使用手冊在畫面上呈現得支離破碎，每一行都是一個帶間距的段落。

**根因**：自製渲染器逐行處理，沒有實作「空行才代表段落結束」的標準 markdown 語意。原始檔案裡一段文字為了排版而手動換行，就被拆成好幾段。

**修法**：用段落緩衝（paragraph buffer），遇到空行或下一個區塊才輸出；清單項目的續行併回上一個項目。

**連帶**：這個渲染器**不支援 `1.` 數字清單**，也不支援表格。手冊內容一律用 `-` 條列——否則數字清單會被當成一般文字合併成同一段。

### D4. Tailwind v4 會靜默忽略 `tailwind.config.js`

v4 是 CSS-first，設計 token 一律寫在 `index.css` 的 `@theme`。建立 config 檔不會有任何錯誤訊息，你只會發現設定沒生效而反覆除錯。

### D5. 原生日期／時間圖示在深色底上看不見

**症狀**：date/time 輸入框的日曆／時鐘圖示幾乎不可見。

**修法**：全域 CSS 對 `::-webkit-calendar-picker-indicator` 套 `filter: invert(1)`，只翻轉圖示、不動輸入框背景。

**注意**：不要同時對個別輸入框套 `[color-scheme:dark]`，兩者疊加會**再翻轉回黑色**，反而重現原本的問題。

---

## E. 種子與展示資料

### E1. 種子資料違反系統自己的業務規則（犯過兩次）

**症狀**：展示資料重置後，示範的加班申請起始時間早於系統算出的「最早可申請時間」，等於種子資料自己過不了剛加上的防呆。

**根因**：種子 SQL 把示範時刻寫死（18:30／18:00），但那幾天的出勤是 09:05–18:10 → 正常工時結束 18:05 → 休息 30 分鐘後最早 18:35 才能申請。**根本原因不是漏改，是沒有任何測試在驗證種子資料是否通過業務規則**，所以事後才由使用者實測發現。

**修法**（兩者都要）：

1. 種子 SQL 的業務時刻改用**佔位符**，由 seed 腳本呼叫**正式的業務函式**依當下設定算出後代入，不再出現寫死的時刻。
2. 新增**全表掃描**的測試（不是抽查特定日期）：每一筆 `attendances`／`leave_requests`／`overtime_requests` 都以正式的純函式重算一次，比對是否一致。

### E2. 種子資料的日期一律相對於固定錨點

種子資料的所有日期都以 `DATE '2026-08-24'`（虛擬時鐘的重置起點）回推／往後推，**不用 `CURRENT_DATE`**。否則每次重置後，畫面上的年資、授權時間、申請單日期都會跟著真實日期跑，展示劇本就不一致了。

### E3. 申請單時序倒置

**症狀**：展示重置後畫面上出現「送出 8/25、審核 8/12」這種時序矛盾。

**根因**：種子資料漏指定 `created_at`，落到 `DEFAULT now()` 的真實牆鐘時間。

**修法**：所有申請單一律明確指定 `created_at`，且保證 `created_at < reviewed_at`；已核准／已駁回者必有 `reviewer_id`。要有測試釘住。

### E4. 本機跑 e2e 前一定要重置資料庫

**症狀**：同一天內第二次跑 e2e，補打卡測試失敗，畫面顯示「這天已經有一筆待審或已核准的補打卡申請」。

**根因**：**e2e 打的是開發資料庫 `employee_portal`，不是測試資料庫 `employee_portal_test`**（`_test` 只有 pytest 在用）。本機 Docker 資料會持久化，第一次成功的測試留下的申請單，第二次就撞到自己。CI 因為每次都是全新容器所以不會遇到。

**修法**：本機跑 e2e 前一律 `npm run db:reset`。

### E5. 歷史回填必須排在劇本式種子資料之後，且只能補洞不能覆蓋

**症狀**：加回半年份的歷史出勤回填（`db_scripts/backfill_history.py`）後，原本手寫的近兩週劇本（例如陳小華 08/19 的整天特別休假、08/21 的曠職示範）如果被回填悄悄覆寫掉，畫面上的敘事就會跟 `seed_business_data.py` 的註解對不上。

**根因**：`seed_business_data.py` 用具名的原始輸入手刻少數幾天的劇本（配合真實的業務函式算出衍生值），回填則是用固定亂數種子（`random.Random(42)`）對**同一段時間窗**（2026-05-01 ~ 08-23）逐工作日隨機生成 normal／late／absent／請假。兩者的日期範圍本來就會重疊。

**修法**：
1. 呼叫順序上，`run_backfill()` 一定要排在 `seed_business_data()` 手寫劇本**之後**。
2. 回填的批次寫入一律用 `INSERT ... ON CONFLICT (user_id, punch_date) DO NOTHING`，不能用 `attendance_repository.upsert_attendance()`（那支是「先查、有列就 UPDATE」，會覆蓋掉劇本資料）。
3. `leave_requests` 沒有能擋重複的唯一鍵，理論上回填的隨機請假可能跟劇本指定的請假撞在同一天，機率極低（各 5%）且純屬展示資料的美觀瑕疵，接受不特別處理。

### E6. e2e 不能對共用、無隔離的開發資料庫平行執行

**症狀**：CI 的 e2e job 間歇性失敗，同一支測試（`admin.spec.js` 授權後即時生效那支）在多次執行裡有時全綠、有時卡在等某個選單連結出現，本地重跑或單獨跑該檔又會過。

**根因**：`playwright.config.js` 設了 `fullyParallel: true`，CI 預設會開兩個以上的 worker——但這與 E4 是同一個限制的另一面：e2e 打的是**同一份沒有交易隔離的開發資料庫**，`fullyParallel: true` 讓 Playwright 連同一個 spec 檔裡的不同測試都可能被排進不同 worker 同時執行，兩個測試同時打同一批固定 seed 帳號（陳小華、admin 等）就會互相干擾或在 CI 有限的 CPU 下把回應拖到超過斷言的 timeout。**舊版 `employee-portal` 已經因為同樣的原因把 e2e 設定寫死成 `fullyParallel: false, workers: 1`**（見它的 `e2e/playwright.config.js` 註解），v2 重建時沒有把這個決策一併搬過來，等於重新踩了一次已經解決過的坑。

**修法**：`fullyParallel: false` 且 `workers: 1`，e2e 全部依檔名序循序執行，用時間換取決定性。這會讓 CI 的 e2e job 變慢（測試數不多，實測仍在可接受範圍），但比起「間歇性紅燈、每次都要重跑確認是不是真的壞掉」划算得多。**不要因為某次 e2e 綠燈就以為這裡沒問題**——沒開這個設定時，失敗與否很大程度上是運氣（CI runner 那次剛好排到同 worker 或剛好夠快）。

---

## F. 效能

### F1. 資料庫與後端跨區部署，把小問題放大 20 倍

**症狀**：正式站「喚醒後仍然卡卡的」，`/api/attendance/today` 要 4–7 秒。

**根因（兩個因素相乘）**：

1. **地區錯置**：後端在 Render 美東、資料庫在 Neon 新加坡，一次查詢往返約 400ms。
2. **依序查詢**：單一使用者單一日期的「今日狀態」查詢，內部卻跑了 9~10 個**彼此互不依賴、卻依序 await** 的查詢（那個解析函式原本是為批次查詢設計的，被單日查詢直接借用）。

9 × 400ms ≈ 4 秒。

**修法**（效果依序）：

1. **資料庫與後端放同一個地區**——這是最高槓桿的一步，光這步就快了 2.5~4 倍。
2. 互不依賴的查詢用 `asyncio.gather()` **併發送出**，總耗時趨近最慢的一個而非全部加總。

**注意**：併發送出會讓單一請求同時佔用多條連線池連線（預設上限 10）。多人同時操作時超出的部分會排隊等待（不會出錯），但在資源受限的環境要留意。

### F2. bcrypt 是 CPU-bound，會拖住事件迴圈

`SALT_ROUNDS = 10` 在受限的免費方案 CPU 上約需 300–400ms，而雜湊函式是同步阻塞的。單人操作無感，但高併發時會排隊。這是可接受的安全成本，不要為此降低 rounds。

---

## G. 部署

### G1. GitHub CLI 預設 token 沒有 `workflow` scope

**症狀**：第一次 push 被拒絕，訊息是 `refusing to allow an OAuth App to create or update workflow .github/workflows/ci.yml without workflow scope`。

**修法**：`gh auth refresh -h github.com -s workflow` 補授權後再推。

### G2. Vercel 把 monorepo 誤判成「多服務」專案

**症狀**：匯入專案時出現 `vercel.json required to deploy projects with multiple services`，要求用 Services 實驗性 schema。

**根因**：這是 npm workspaces monorepo（`frontend/`、`backend/` 並存），Vercel 偵測到多個可部署子專案。

**修法**：本專案不需要那個功能（後端獨立部署在 Render）。回歸標準做法：**Vercel 專案的 Root Directory 設為 `frontend`**，讓它當成單純的子目錄專案處理。對應要有一份 `frontend/vercel.json`（只含 SPA 的 rewrites 規則）。

### G3. Root Directory 改了，Build Command 沒跟著改

**症狀**：`vite build` 明明成功印出 `dist/index.html` 等產物，Vercel 卻回報「找不到 Output Directory」。

**根因**：Build Command 還殘留 `npm install && npm run build --workspace frontend`（Root Directory 為專案根目錄時才需要的寫法），與新的 Root Directory 疊加後路徑對不上。

**修法**：關掉 Build Command 的 Override，用框架偵測到的預設值；Output Directory 維持 `dist`（相對於 Root Directory，不要再寫 `frontend/dist`）。

### G4. push 到 GitHub 不會自動更新雲端資料庫

Render 的自動部署只會重建**應用程式碼**，`render.yaml` 的 buildCommand 裡沒有任何一步會跑 migration。新增 migration 後必須手動對正式資料庫執行一次：

```bash
DATABASE_URL="<neon 連線字串>" npm run db:migrate
```

且順序要**先 migrate 再讓新程式碼上線**，否則會有一段「新程式碼碰到舊 schema」的空窗期。

> 純種子資料的變更則不需要手動下指令：部署新程式碼後，在畫面上點「重置展示資料」即可套用新的種子邏輯。

### G5. 免費方案的冷啟動

Render 免費方案長時間無人使用後，第一次請求會有數十秒的冷啟動延遲。前端要有「喚醒中」的橫幅提示（請求超過 3 秒才顯示，避免正常請求也閃一下）。

### G6. CI 的 artifact 路徑要與實際輸出對齊

前一版的 CI 設定把 Playwright 失敗截圖的上傳路徑寫成 `e2e/test-results`，但實際輸出在專案根目錄的 `test-results/`，導致每次失敗都顯示「No files were found」，從來沒真的收集到診斷資料。設定完要實際製造一次失敗來驗證。

---

## H. 除錯方法論

這一版累積的兩個教訓，值得寫下來：

1. **症狀相似不代表根因相同。** e2e 失敗時間點剛好落在效能優化之後，就被誤判為效能問題；直到用 `git checkout` 把程式碼退回舊版、問題依然重現，才排除嫌疑。**改動與症狀在時間上相關，不等於因果。**

2. **看真正的錯誤訊息，不要只看測試框架的斷言失敗。** 那次 e2e 的表面現象是「等待導頁逾時」，真正的訊息「補打卡日期不得為未來日期」印在畫面上，要打開 Playwright 的 error-context 才看得到。**逾時類的失敗幾乎都有更底層的原因。**
