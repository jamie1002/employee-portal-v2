# Employee Portal — 專案守則

這是「企業員工管理與出勤系統」的重建版本。本檔是給 AI 開發代理的常駐守則，每次對話都會被載入。

## 這個專案是什麼

一套公開展示用的企業員工管理與出勤系統，涵蓋打卡、請假／加班／補打卡申請與審核、場地借用、員工與部門管理、細粒度權限下放。定位是**作品集展示**，不是內部生產系統——所有資料都是種子生成的展示資料，任何訪客都能用固定的展示帳號登入操作。

規格文件的分工：

| 文件 | 內容 |
| :--- | :--- |
| `SPEC.md` | 系統行為的單一事實來源：權限矩陣、資料表、API 契約、業務規則、錯誤碼 |
| `docs/UI-SPEC.md` | 頁面版面、使用情境、元件契約、design token、響應式斷點規範 |
| `docs/PITFALLS.md` | **實作前必讀**。前一版踩過的坑，全部是實測才發現、規格上看不出來的 |
| `docs/PROMPT-ENGINEERING.md` | **改 AI 助理的提示詞或工具前必讀**。本專案規範 LLM 的手法、失敗過的寫法與修改流程 |
| **`docs/RUNBOOK.md`** | **重建的執行腳本與進度追蹤**。不確定現在做到哪一步時看這份 |
| `docs/REBUILD-TASKS.md` | 重建批次的範圍與驗收條件（RUNBOOK 的詳細版） |
| `docs/USER_GUIDE.md` | 使用者手冊，登入頁會直接渲染它 |
| `README.md` | 架構說明、本機啟動、技術決策、雲端部署 runbook |

## 技術棧（版本鎖定，不得自行升級）

**後端**：Python 3.12 + FastAPI 0.115.6 + uvicorn 0.34.0 + asyncpg 0.30.0（**無 ORM，手寫 SQL**）+ pydantic 2.10.4 + pydantic-settings 2.7.1 + bcrypt 4.2.1 + PyJWT 2.10.1 + aiosmtplib 3.0.2 + structlog 24.4.0 + APScheduler 3.11.0 + openpyxl 3.1.5

**前端**：React 19.2.8 + Vite 8.2.2 + React Router 7.18.2 + Tailwind CSS 4.3.3（`@tailwindcss/vite`）+ axios + date-fns 4.4.0 + lucide-react

**資料庫**：PostgreSQL 16（本機用 Docker，雲端用 Neon.tech）

**測試**：pytest 8.3.4 + pytest-asyncio 0.25.1 + pytest-timeout 2.3.1 + httpx 0.28.1（後端）／Vitest 4.1.11 + Testing Library（前端）／Playwright 1.62.1（e2e）

### 三個版本陷阱

1. **Tailwind v4 是 CSS-first**：設計 token 一律寫在 `frontend/src/index.css` 的 `@theme` 區塊。**不要建立 `tailwind.config.js`**，v4 會靜默忽略它，你會以為設定沒生效而反覆除錯。
2. **React Router v7** 的 API 與 v6 有差異，不要套用 v6 的寫法。
3. **asyncpg 的型別邊界**：`DATE`／`TIME`／`TIMESTAMPTZ` 欄位的查詢參數**必須是原生 Python 物件**（`datetime.date`／`datetime.time`／`datetime`），傳字串會拋型別錯誤。專案有 `app/utils/pg_types.py` 集中處理轉換，一律走它。

## 架構慣例

```
employee-portal-v2/
├── backend/app/
│   ├── routers/       # HTTP 層：只負責解析請求、掛權限 dependency、回傳格式化結果
│   ├── services/      # 業務邏輯層：所有規則、驗證、跨表協調都在這裡
│   ├── repositories/  # 資料存取層：手寫 SQL，不做授權判斷
│   ├── schemas/       # 手刻的請求驗證函式（parse_*），不用 pydantic model 做請求驗證
│   ├── middleware/    # 認證授權、錯誤處理、安全標頭
│   ├── utils/         # 時區、虛擬時鐘、JWT、密碼雜湊、錯誤類別、PG 型別轉換
│   ├── config/        # 環境變數、連線池、業務資料表清單
│   ├── jobs/          # APScheduler 排程任務
│   └── db_scripts/    # migrate / seed / reset 的 CLI 入口
├── frontend/src/
│   ├── pages/         # 路由對應的頁面元件
│   ├── components/    # 共用元件
│   ├── hooks/         # 自訂 hook
│   ├── api/           # axios 封裝，每個模組一個 *.api.js
│   ├── context/       # AuthContext
│   └── utils/         # 前端共用工具
├── db/
│   ├── migrations/    # 依序編號的 SQL（每支都必須可重複執行）
│   └── seed/          # 展示種子資料
├── e2e/               # Playwright
└── docs/
```

**分層紀律**：
- Router **不做業務判斷**，只掛 dependency 與呼叫 service。
- Service **不直接寫 SQL**，透過 repository。
- Repository **不做授權判斷**（範圍限縮是 service 的責任）。
- 純函式（工時計算、時數計算等）獨立於 I/O，可單獨單元測試。

## 語言規範

- **一律使用繁體中文**：對話、程式碼註解、docstring、文件、系統輸出訊息（log／API 錯誤訊息）。
- **嚴禁簡體中文**，包含用字習慣（「資料」不是「数据」、「程式」不是「程序」）。
- 專有名詞（HTTP、JWT、UPSERT、CHECK constraint 等）維持英文。
- 註解要寫**為什麼這樣做**，不是重述程式碼在做什麼。特別是「刻意不那樣做」的決策，一定要留下理由。

## 硬性規則（違反就是 bug）

### 時間與時區

- **所有「今天是哪一天」的判斷一律走 `get_business_date(moment, tz='Asia/Taipei')`**，禁止直接用 UTC 日期。台灣時間 08:00 對應 UTC 前一日 00:00，用 UTC 日期會把早班打卡記到前一天，並沿著 `UNIQUE(user_id, punch_date)` 污染後續的補打卡目標列。
- **所有業務時間戳一律取自 `get_virtual_now()`**（展示用虛擬時鐘），禁止用 `datetime.now()`、SQL 的 `now()` 或資料庫觸發器。這包含打卡時間、申請單 `created_at`、審核 `reviewed_at`、排程判斷的「今天」。
  - **唯一例外**：展示資料閒置自動重置的計時器，刻意用真實時間（`time.monotonic()`）——虛擬時間到達 clamp 上限後就不再前進，用它會讓重置機制永遠不觸發。
- 資料庫時間欄位一律 `TIMESTAMPTZ`，不用 `TIMESTAMP`。

### 考勤規則

- **禁止在程式碼中寫死時間字面值**：`09:00`、`18:00`、`12:00`、`13:00`、`10`（分鐘）、`8`（小時）等一律讀 `system_settings`。
  - 驗收方式：把設定改成「08:30–17:30、緩衝 15 分、午休 12:30–13:30」，所有規則要整體平移，測試必須有一組非預設設定跑同一套斷言。
- **例外**（法規／產品常數，維持具名常數並在註解說明為何不是設定值）：
  - `OVERTIME_REST = timedelta(minutes=30)`（加班前的休息時間）
  - 加班時數的 30 分鐘捨去單位
  - `LATE_PUNCH_OUT_MARGIN = timedelta(hours=1)`（晚下班提示門檻，非計薪規則）

### 安全

- **權限絕不寫進 JWT**。`get_current_user()` 每個請求都回資料庫重查角色與權限，這是「收回權限即時生效」的前提。
- **前端的 `RoleGate`／選單過濾只是 UX，不是安全邊界**。每一支端點都必須自己掛權限 dependency。
- **範圍限縮一律 deny-by-default**：寫「不是 admin 就限縮部門」，不要寫「是 manager 才限縮」——後者一旦出現第四種身分就自動變成不限縮。
- 前端**禁止使用 `dangerouslySetInnerHTML`**，也不引入第三方 markdown 套件。
- 密碼一律 bcrypt（`SALT_ROUNDS = 10`），錯誤訊息不得洩漏「帳號不存在」與「密碼錯誤」的差別。

### 資料庫

- **每支 migration 都必須可重複執行**：`CREATE TABLE IF NOT EXISTS`、`ADD COLUMN IF NOT EXISTS`、`ON CONFLICT DO NOTHING`；CHECK 約束用「先 `DROP CONSTRAINT IF EXISTS` 再 `ADD CONSTRAINT`」。**這個專案沒有 `schema_migrations` 版本表，每支 `.sql` 每次都會全部重跑。**
- UPSERT 更新既有列時，**未提供的欄位一律用 `COALESCE($n, 欄位名)` 保留原值**，不要直接覆蓋成傳入值——漏寫會造成靜默資料遺失，比回 500 更難察覺。
- `NUMERIC` 欄位在 asyncpg 設定為解碼成**字串**（保留 `"8.00"` 的固定小數位），不要改成 float 或 Decimal，前端顯示與測試斷言都依賴這個格式。

### 測試

- **後端測試一律打真實 PostgreSQL，禁止 mock 資料庫**。這個專案的風險集中在 SQL 語意本身（UPSERT 覆蓋語意、排除約束、唯一鍵衝突、時區轉換），mock 掉等於把要測的東西測掉了。
- 測試資料庫（`employee_portal_test`）與開發資料庫（`employee_portal`）**完全隔離**，且在執行任何破壞性操作前必須驗證資料庫名稱以 `_test` 結尾。
- **前端元件測試可以 mock API 層**（那一層測的是元件邏輯，不是 SQL 正確性）。
- **e2e 測試的日期一律以虛擬時鐘的固定錨點推算，禁止使用 `new Date()`**——真實日期會隨時間往前走，遲早超過虛擬時鐘的固定窗口而讓測試整批失效。

## 統一指令入口

一律透過根目錄的 npm scripts，不要各自 `cd` 進子目錄下指令：

```bash
npm run dev              # 前後端同時啟動
npm run db:migrate       # 執行遷移
npm run db:seed          # 寫入種子資料
npm run db:reset         # migrate + seed（跑 e2e 前必做）
npm run test:backend     # pytest
npm run test:frontend    # Vitest
npm run test:e2e         # Playwright
npm test                 # 後端 + 前端
```

## 開發流程

**這個專案正在從既有版本重建中。** 完整的執行順序見 **`docs/RUNBOOK.md`**——那份是逐批的指令腳本，每批要做什麼、驗收指令是什麼、下一步是什麼都寫在裡面。批次的範圍與驗收條件見 `docs/REBUILD-TASKS.md`。

**重建期間不使用 OpenSpec 流程**（`/opsx:*`）：規格已經完整寫在 `SPEC.md` 與 `docs/UI-SPEC.md`，再跑一次 propose → design → tasks 只是把寫好的東西重新推導一遍。`openspec/` 目錄保留給重建**完成後**的新功能使用。

每完成一個功能群組就跑對應測試，不要整批寫完才第一次跑。每批結束跑完整檢查點：

```bash
npm run db:reset && npm test && npm run test:e2e
```

使用者的終端機是 **Windows PowerShell 5.1，不支援 `&&`**。給他手動執行的指令一律用 `;` 串接。
