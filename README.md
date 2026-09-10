# Employee Portal

企業員工管理與出勤系統 —— 涵蓋打卡、請假／加班／補打卡申請與審核、場地借用、員工與部門管理、細粒度權限下放，並附完整的雲端部署設定與三層測試。

**線上展示**：[employee-portal-v2-frontend.vercel.app](https://employee-portal-v2-frontend.vercel.app)（登入頁有一鍵代入的展示帳號，密碼統一 `Demo1234`）

| 文件 | 用途 |
| :--- | :--- |
| [`SPEC.md`](SPEC.md) | 系統規格：權限矩陣、資料表、API 契約、業務規則、錯誤碼 |
| [`docs/UI-SPEC.md`](docs/UI-SPEC.md) | 介面規格：版面、使用情境、元件契約、design token、響應式斷點 |
| [`docs/PITFALLS.md`](docs/PITFALLS.md) | 踩坑紀錄，實作前必讀 |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | 重建的執行腳本與進度追蹤 |
| [`docs/REBUILD-TASKS.md`](docs/REBUILD-TASKS.md) | 重建批次的範圍與驗收條件 |
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | 使用者手冊（登入頁會直接渲染它） |
| [`CLAUDE.md`](CLAUDE.md) | AI 開發代理的常駐守則 |

---

## 功能總覽

| 模組 | 說明 |
| :--- | :--- |
| 出勤打卡 | 上下班打卡、彈性工時計算（雙向緩衝、浮動午休）、遲到／早退／缺勤判定 |
| 補打卡 | 忘記打卡時提出申請，主管核准後以「生效值」覆蓋顯示，原始打卡事實不變 |
| 請假 | 四種假別、逐工作日時數計算（排除週末與國定假日）、假別配額（特休依勞基法年資制） |
| 加班 | 30 分鐘為單位、扣除午休重疊、起算點防呆 |
| 審核 | 三種申請單統一狀態機、部門範圍限制、禁止自審（admin 豁免） |
| 場地借用 | 時間軸視覺化、應用層預檢 + 資料庫排除約束雙層防重複 |
| 員工資訊 | 全公司通訊錄（全員可查）、帳號與部門管理（admin） |
| 細粒度權限 | admin 可將國定假日／考勤設定／匯出報表個別下放給特定員工 |
| 匯出報表 | 五種資料類型、欄位勾選、`.xlsx`，範圍 deny-by-default |
| 展示機制 | 可調虛擬時鐘、展示資料一鍵重置與閒置自動重置 |
| AI 助理 | 依公司政策文件（考勤規則、請假辦法、產品目錄、公司簡介）回答問題，RAG 架構、附引用來源，唯讀不碰個人資料 |

---

## 架構

```
使用者瀏覽器
    │
    ▼
Vercel（frontend，靜態 SPA）
    │  fetch /api/*
    ▼
Render（backend，FastAPI，免費方案會冷啟動）
    │
    ▼
Neon.tech（PostgreSQL，Serverless）
```

前後端為不同網域，因此認證採 **Bearer Token**（存於 `localStorage`）而非 Cookie——跨網域的 Cookie 會受瀏覽器第三方 Cookie 限制影響。

### 目錄結構

```
├── backend/app/
│   ├── routers/       HTTP 層（只解析請求、掛權限、回傳）
│   ├── services/      業務邏輯層（所有規則都在這裡）
│   ├── repositories/  資料存取層（手寫 SQL，不做授權）
│   ├── schemas/       手刻的請求驗證函式
│   ├── middleware/    認證授權、錯誤處理、安全標頭
│   ├── utils/         時區、虛擬時鐘、JWT、密碼、PG 型別
│   ├── config/        環境變數、連線池
│   ├── jobs/          APScheduler 排程
│   └── db_scripts/    migrate / seed / reset
├── frontend/src/      pages / components / hooks / api / context / utils
├── db/                migrations / seed
├── e2e/               Playwright
└── docs/
```

### 技術棧

- **後端**：Python 3.12、FastAPI、`asyncpg`（原生 SQL，無 ORM）、PyJWT、bcrypt、structlog、APScheduler、openpyxl
- **LLM**：`google-generativeai==0.8.6`（AI 助理用，官方新 SDK `google-genai` 會破壞版本鎖定，見 `docs/PITFALLS.md` I1）
- **前端**：React 19、Vite、React Router 7、Tailwind CSS v4（CSS-first）、axios、date-fns
- **資料庫**：PostgreSQL 16 + pgvector extension
- **測試**：pytest（真實 Postgres）、Vitest + Testing Library、Playwright

---

## 本機啟動

需要 Node.js 20+、Python 3.12、Docker。

```bash
docker compose up -d                          # 啟動本機 PostgreSQL（開發 5442 / 測試 5443，避開舊專案佔用的 5432/5433）
cp .env.example .env
npm install
pip install -r backend/requirements.txt
npm run db:reset                              # migrate + seed
npm run dev                                   # 前後端同時啟動
```

**AI 助理功能**需另外設定 `GOOGLE_API_KEY`（`.env`，到 https://aistudio.google.com/apikey 申請）並跑一次 ingest（把政策文件切段、算 embedding 寫入資料庫，是唯一會呼叫 Gemini API 的批次作業）：

```bash
npm run db:ingest
```

留空 `GOOGLE_API_KEY` 不影響其他功能，AI 助理頁面會顯示「目前無法使用」並優雅降級（503 `CHAT_UNAVAILABLE`）。

開啟 `http://localhost:5173`，用展示帳號登入：

| 角色 | 帳號 | 密碼 |
| :--- | :--- | :--- |
| 系統管理者 | `admin@demo.com` | `Demo1234` |
| 部門主管 | `manager@demo.com` | `Demo1234` |
| 一般員工 | `employee@demo.com` | `Demo1234` |

三組展示帳號密碼一律相同（`Demo1234`），登入頁也提供一鍵代入按鈕不需手動輸入。

### 指令一覽

```bash
npm run dev            # 前後端同時啟動
npm run db:migrate     # 執行遷移
npm run db:seed        # 寫入種子資料
npm run db:reset       # migrate + seed（跑 e2e 前必做）
npm run db:ingest      # AI 助理語料 embedding（唯一會呼叫 Gemini API 的批次作業，需 GOOGLE_API_KEY）
npm run test:backend   # pytest
npm run test:frontend  # Vitest
npm run test:e2e       # Playwright
npm run eval:chat      # AI 助理黃金題庫評估（72 題，需 GOOGLE_API_KEY，不進 CI）
npm test               # 後端 + 前端
```

---

## 技術決策與取捨

### 無 ORM，手寫 SQL

資料存取層以 `asyncpg` 手寫 SQL。這不是「還沒導入 ORM」，是刻意的選擇——本系統最關鍵的幾個正確性保證都依賴 PostgreSQL 的特定行為，ORM 抽象反而是阻礙：

- `room_bookings` 的 `EXCLUDE USING gist` 排除約束（防重複預約的資料庫層保證）
- UPSERT 的 `COALESCE` 語意（補打卡只補單邊時不得清空另一邊）
- `NUMERIC` 的解碼行為（必須保留 `"8.00"` 的固定小數位字串）
- `AT TIME ZONE 'Asia/Taipei'` 的營業日推導

代價是每個 repository 函式都要手寫 SQL、型別安全較弱。這個取捨在本專案是划算的，因為最複雜的邏輯剛好都是 ORM 處理得最彆扭的部分。

### 出勤資料純衍生

`attendances` 只保存「原始打卡事實」，補打卡與請假核准**不覆寫**這張表；異動後的「生效值」在讀取時 join 已核准申請單即時算出。

**為什麼**：如果核准時就覆寫出勤紀錄，原始事實會永久遺失，而「原始打卡是幾點」在稽核上是需要的。曾經的替代方案是加 `original_punch_*` 欄位保存覆蓋前的值，但那等於同一份事實存兩份、還要維護兩者的同步；改成讀取時計算，資料表只有一個事實來源，代價是每次讀取多幾個 join。

### 早退零寬限，緩衝時間只作用在到班端

`grace_period_minutes` 是**雙向**的：晚到在緩衝內算準時、早到超過緩衝的部分不計入工時，午休與正常工時結束時間也跟著同步平移。但**下班端完全沒有寬限**——一天該做滿的工時就是要做滿到那一刻，表定下班 18:00 就是 18:00，17:55 打卡一樣算早退。

這個不對稱是刻意的：到班端的緩衝是為了容忍通勤誤差並讓午休跟著移動，跟「工時要不要做滿」是兩回事。

### 早退用獨立布林欄位，不擴充 `status` 列舉值

遲到與早退可以同時成立（09:30 上班、17:00 下班）。塞進同一個 `status` 欄位會互相覆蓋，只能顯示其中一個。因此早退獨立為 `is_early_leave` 布林欄位，與 `status` 並存。

### 兩套午休邏輯：出勤浮動、請假固定

出勤打卡的午休會隨到班時間在緩衝範圍內平移；請假時數的午休則**固定不動**。

**為什麼刻意不一致**：請假通常是事先申請，當天沒有實際打卡時間可以作為浮動的基準。硬要浮動只會讓「這筆假到底算幾小時」變得比規則本身更難解釋。但請假的**工作時間窗**一樣享有緩衝（只在整個請假區間的頭尾兩端套用，中間日維持表定時間）。

### 權限即時生效，不寫進 JWT

`get_current_user()` 每個請求都回資料庫重查角色與權限，token payload 內的值不被信任。

**為什麼不放進 token**：token 有效期內收回的權限不會失效，要嘛縮短 token 壽命、要嘛做黑名單，兩者都比「本來就要做的那次查詢」貴。既然每個請求本來就要查一次使用者，權限用 `LEFT JOIN LATERAL` 跟著同一次查詢帶出，**不增加網路往返**，換到的是「收回即時生效、不需重新登入」。

### 細粒度權限，不新增角色

三個可下放的功能任意組合會是 8 種角色，RBAC 矩陣直接爆炸。而且新增角色與「唯一管理者，不設代理人」的設計衝突——那條規則講的是不做多管理者互相制衡，這裡下放的是單項操作權，不是管理者身分。

### 唯一管理者，不設代理人

系統同時只允許存在一位 `admin`（`SINGLE_ADMIN_ONLY`），並保留「最後一位管理者不能被降級」的保護（`LAST_ADMIN_PROTECTED`），避免零管理者的死局。

連帶影響禁止自審規則：admin 沒有代理人可以審核自己的申請，因此**豁免**禁止自審；待審清單對 admin 也必須包含自己送出的申請，否則這條豁免會是死 code。

### 場地預約兩層防護

應用層 SELECT 預檢（給人看的友善訊息）+ 資料庫排除約束（給機器的正確性保證）。

**為何兩層都要**：只有應用層預檢時，兩個並行請求可能同時通過檢查（此時都還沒 INSERT）然後都寫入成功——典型的 TOCTOU 競態。反過來只靠資料庫約束，使用者只會收到 PostgreSQL 內部格式的錯誤。錯誤處理器把 `23P01` 轉譯為 409。

### 可調的展示虛擬時鐘

公開展示環境無法要求訪客「假裝現在是星期三」。系統的「現在」改為可調的虛擬時鐘（`虛擬錨點 + 真實流逝時間`，clamp 在 2026-08-24～08-31），全面取代所有業務時間來源。

**唯一例外**：展示資料閒置自動重置的計時器刻意使用真實時間——虛擬時間到達 clamp 上限後不再前進，用它會讓重置機制永遠不觸發。

### 種子資料以業務規則驗證，不靠人工抽查

種子 SQL 的業務時刻一律用佔位符，由 seed 腳本呼叫**正式的業務函式**算出後代入；另有全表掃描的測試，把每一筆種子資料以正式純函式重算一次比對。

**為什麼**：寫死示範數字的做法，會在系統加上新防呆時讓種子資料自己過不了自己的規則，而且只有等到有人實機測試才會發現。補測試才是根治。

### 測試不 mock 資料庫

後端測試一律打真實 PostgreSQL。本專案的風險集中在 SQL 行為本身（UNIQUE 衝突、UPSERT 覆蓋語意、排除約束、時區轉換），mock 掉資料庫等於把要測的東西測掉了。測試資料庫與開發資料庫完全隔離，且執行破壞性操作前驗證資料庫名稱以 `_test` 結尾。

前端元件測試則**可以**mock API 層——那一層要驗證的是「元件收到某個回應時畫面對不對」，跟 SQL 正確性是兩件事。

---

## 雲端部署

- **前端（Vercel）**：Root Directory 設為 `frontend`，`frontend/vercel.json` 提供 SPA 路由改寫
- **後端（Render）**：`render.yaml`，`healthCheckPath` 指向 `/api/health`
- **資料庫（Neon.tech）**：連線字串自動偵測非本機 host 以啟用 SSL。**務必與 Render 選同一個地區**，跨區部署會讓每次查詢多付數百毫秒
- 正式環境（`ENVIRONMENT=production`）若 `CORS_ORIGINS` 未設定或為 `*`，應用程式啟動時直接終止（`AppSettings` 的 model_validator）

### 首次上線流程

機密值一律不進版控（`.env` 已被 `.gitignore` 排除）。

1. **GitHub**：`gh auth login --web`，若 repo 含 `.github/workflows/` 需先 `gh auth refresh -h github.com -s workflow` 補授權，再 `gh repo create <name> --public --source=. --remote=origin --push`
2. **Neon**：建立專案（**選 US East (Ohio)**——`render.yaml` 已把 Render 服務的 `region` 釘在 `ohio`，Neon 的 US East 選項要跟著選 Ohio 而非 N. Virginia，否則跨區會讓每次查詢多付數百毫秒），取得 pooled connection string；本機執行一次：
   ```bash
   DATABASE_URL="<neon-connection-string>" npm run db:migrate
   DATABASE_URL="<neon-connection-string>" npm run db:seed
   GOOGLE_API_KEY="<key>" DATABASE_URL="<neon-connection-string>" npm run db:ingest
   ```
   `db:ingest` 這步**不能省略也不能延後**：忘了跑不會報錯，AI 助理會對每一題都正常回「查無相關規定」，看起來像功能正常，其實是語料是空的（見 `docs/PITFALLS.md` I3）。跑完驗證 `SELECT count(*) FROM policy_embeddings;` 應為 61 筆。
3. **Render**：New → Blueprint → 選 repo（自動讀 `render.yaml`），填入 `DATABASE_URL`、`JWT_SECRET`（`openssl rand -base64 48` 自行產生）、`CORS_ORIGINS`（先填佔位）、`GOOGLE_API_KEY`（AI 助理用，留空則該功能優雅降級不影響其他頁面）
4. **Vercel**：匯入同一個 repo，**Root Directory 設為 `frontend`**，環境變數 `VITE_API_BASE_URL` = `https://<render 網址>/api`
5. 回 Render 把 `CORS_ORIGINS` 改成 Vercel 正式網址（不要有結尾斜線）
6. 驗證：`curl https://<render>/api/health` 應回 `"database":"connected"`

### 後續維運

- **只改種子資料**：push → Render 自動部署 → 在畫面上點「重置展示資料」即可套用，不需手動下指令
- **新增 migration**：push 不會自動更新資料庫，必須手動對正式庫執行一次 `DATABASE_URL="..." npm run db:migrate`，且要**先 migrate 再讓新程式碼上線**
- **修改政策文件語料**（`db/policy_docs/*.md`）：push 不會自動重新 embedding，必須手動對正式庫執行一次 `GOOGLE_API_KEY="..." DATABASE_URL="..." npm run db:ingest`（只對內容有變的段落重算，不是全量重跑），並重新跑一次 `npm run eval:chat` 確認黃金題庫仍然全綠

---

## CI

`.github/workflows/ci.yml` 在 push／PR 時執行：起兩個 PostgreSQL 服務容器 → migrate + seed → 後端 pytest → 前端 Vitest → 前端 build → Playwright e2e。本機與 CI 使用**完全相同的 npm 指令**，不另寫第二份初始化流程。

e2e 刻意設定 `fullyParallel: false`、`workers: 1` 循序執行（見 `playwright.config.js`）：e2e 打的是同一份沒有交易隔離的開發資料庫，平行 worker 會讓測試互相干擾造成間歇性失敗（見 `docs/PITFALLS.md` E6）。這會讓 e2e job 變慢，但比起「間歇性紅燈、每次都要重跑確認是不是真的壞掉」划算。

CD 不另外寫部署腳本——Vercel 與 Render 都原生支援「接上 GitHub repo 後，push 到追蹤分支即自動建置部署」。

---

## 已知範圍限制

- 假別配額的計算公式（特休依年資、事病假依曆年制）寫死在後端，不開放畫面調整
- 資料模型只支援「一天一筆打卡紀錄」，不支援跨越午夜的班別
- 申請單送出後不能自行撤回，只能等審核結果
- 「處理私人事務」的備註只寫入固定文字，不支援自訂內容
- 展示環境的資料庫為所有訪客共用，會定期自動重置
- 登入憑證存於 `localStorage`，可被同網域的 JavaScript 讀取。系統本身不使用任何略過安全轉義的渲染方式，但這仍是公開展示環境，請勿輸入真實個人敏感資訊
- AI 助理**只回答公司政策文件範圍內的問題**，不查詢任何個人出勤／假別／申請資料（該功能規劃中，尚未實作）；語料為虛構示範內容，公司名稱與前端標題不一致（「暖丘生活」vs. Employee Portal），刻意不統一以保留 `content_hash` 與黃金題庫的有效性
