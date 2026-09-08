# Employee Portal 系統規格

本文件描述系統的**最終狀態**，是系統行為的單一事實來源。實作前請一併閱讀 `docs/PITFALLS.md`。

---

## 1. 系統定位

公開展示用的企業員工管理與出勤系統。任何訪客都能用固定的展示帳號登入，在一個固定的展示劇本（2026-08-24 ~ 2026-08-31）內體驗完整的打卡、請假、補打卡、加班、場地借用流程。

**因為是公開展示環境，衍生三個關鍵設計**：

1. **展示用虛擬時鐘**：系統的「現在」不是伺服器真實時間，而是可由任何登入者調整的虛擬時鐘（範圍 clamp 在展示視窗內）。訪客不可能被要求「假裝現在是星期三」，所以時間必須可調。
2. **展示資料可一鍵重置**：`admin` 可手動重置，正式環境另有閒置自動重置。資料被玩亂是預期行為，不是故障。
3. **三組展示帳號固定不可變更密碼**：`admin@demo.com`／`manager@demo.com`／`employee@demo.com`，`is_first_login` 恆為 `false`。

---

## 2. 技術棧

| 層 | 技術 |
| :--- | :--- |
| 前端 | React 19.2.8、Vite 8.2.2、React Router 7.18.2、Tailwind CSS 4.3.3（CSS-first，無 config 檔）、axios、date-fns |
| 後端 | Python 3.12、FastAPI 0.115.6、uvicorn 0.34.0、asyncpg 0.30.0（**無 ORM，手寫 SQL**）、PyJWT、bcrypt、structlog、APScheduler、openpyxl |
| 資料庫 | PostgreSQL 16（本機 Docker／雲端 Neon.tech） |
| 部署 | 前端 Vercel、後端 Render、資料庫 Neon.tech |

### 2.1 為何不使用 ORM

資料存取層以 `asyncpg` 手寫 SQL，理由是本系統最關鍵的幾個正確性保證都依賴 PostgreSQL 的特定行為，ORM 抽象反而是阻礙：

- `room_bookings` 的 `EXCLUDE USING gist` 排除約束（防止重複預約的資料庫層保證）
- UPSERT 的 `COALESCE` 語意（補打卡只補單邊時不得清空另一邊）
- `NUMERIC` 的解碼行為（必須保留 `"8.00"` 的固定小數位字串）
- `AT TIME ZONE 'Asia/Taipei'` 的營業日推導

### 2.2 前端渲染安全

`docs/USER_GUIDE.md` 會在登入頁以自製的 `SimpleMarkdown` 元件渲染。該元件**只支援**標題（`#`／`##`／`###`）、`-`／`*` 條列、`**粗體**`、`` `行內程式碼` ``、`>` 引言、一般段落。

- **不支援表格，也不支援 `1.` 數字清單**——手冊內容一律用 `-` 條列。
- 一律經 React 輸出轉義，**禁止 `dangerouslySetInnerHTML`**，也不引入第三方 markdown 套件。

---

## 3. 角色與權限

### 3.1 角色權限矩陣

本矩陣描述**角色內建**的權限。其中三項 admin 專屬功能可個別下放給特定使用者，見 §3.4。

| 功能模組 | 員工 (employee) | 主管 (manager) | 系統管理者 (admin) |
| :--- | :--- | :--- | :--- |
| **上下班打卡** | 僅限本人打卡與紀錄檢視 | 僅限本人打卡與紀錄檢視 | 僅限本人打卡，可檢視全公司紀錄 |
| **補打卡** | 提出申請（同日禁止重複）、檢視個人進度 | 審核所屬部門同仁申請 | 審核全公司申請 |
| **請假申請** | 提出申請、查看假況與假別剩餘量 | 審核所屬部門同仁請假 | 審核全體請假、維護國定假日（可下放） |
| **加班申請** | 提出申請（30 分鐘為單位）、查看個人核可時數 | 審核所屬部門同仁加班 | 審核全體加班、匯出報表（可下放） |
| **場地借用** | 預約、取消個人預約 | 預約、取消個人預約 | 預約、強制釋放所有預約時段 |
| **員工資訊** | 查詢全公司通訊錄（唯讀） | 查詢全公司通訊錄（唯讀） | 帳號增修刪、部門設定、考勤設定（可下放）、國定假日增刪（可下放）、權限授予 |

### 3.2 權限實作規範

- **`authenticate`**：解析驗證 `Authorization: Bearer <token>`，將 `{ id, role, department_id, permissions }` 掛載於當前使用者。缺少或無效 token 一律回 **401**。
  - `role`、`department_id`、`permissions` **必須於每次請求自資料庫查出**，不得從 token payload 讀取。token payload 僅含 `{ id, role, department_id, iat, exp }`，其中 role 與 department_id 僅供除錯參考、不被信任。
- **`require_roles(*roles)`**：角色不符一律回 **403**。角色之間**無階層**，admin 不自動繼承 manager，要同時允許必須明列。
- **`require_permission(permission, roles=("admin",))`**：請求者角色命中 `roles`、或持有 `permission`，任一即放行；兩者皆不符回 **403**。兩種失敗回傳**完全相同**的訊息與 code，不揭露是哪一道擋下的。
- **部門範圍檢查**：`manager` 對申請單的審核操作，必須額外驗證「申請人的 `department_id` 等於審核者的 `department_id`」，不符回 **403**。
- **禁止自審（admin 豁免）**：`manager` 不得審核自己送出的申請單，違反回 **403**；`admin` 因系統為唯一管理者、無代理人可審核，**豁免**此限制。
- **匯出範圍 deny-by-default**：`POST /api/exports/{kind}` 除 `admin` 外一律強制注入請求者的 `department_id`（`room-bookings` 類型除外）；未指派部門者回 **403**。

### 3.3 唯一管理者

系統定位為單一管理者自行維運，不設代理人、不走多管理者互相制衡的科層設計。

- **唯一管理者**：`POST /api/users` 或 `PUT /api/users/{id}` 若欲將角色設為 `admin` 且系統已存在其他 `admin`，一律回 **400**（`SINGLE_ADMIN_ONLY`）。
- **最後一位管理者保護**：`PUT /api/users/{id}` 若目標目前是 `admin`、變更後不再是 `admin`、且系統只剩這一位 `admin`，一律回 **400**（`LAST_ADMIN_PROTECTED`）。避免零管理者的死局。
- **admin 自審豁免的連帶影響**：`GET /*/pending` 待審清單對 `admin` 呼叫時**包含自己送出的申請**（對 `manager` 則排除），否則豁免規則會是死 code。
- 前端角色下拉一律不提供 `admin` 選項，admin 帳號列不顯示編輯／刪除入口。

### 3.4 細粒度權限下放

`admin` 可將以下三項原本 admin 專屬的功能，個別授予特定使用者：

| 權限鍵 | 中文名稱 | 涵蓋端點 |
| :--- | :--- | :--- |
| `holidays.manage` | 國定假日管理 | `POST /api/holidays`、`DELETE /api/holidays/{date}` |
| `settings.manage` | 考勤設定 | `PUT /api/settings` |
| `exports.run` | 匯出報表 | `POST /api/exports/{kind}` |

規則：

- 授予／收回**僅限 `admin`**（`PUT /api/users/{id}/permissions`），非 admin 一律 **403**。
- `admin` 恆具備全部權限，**不在 `user_permissions` 留列**；對 admin 授權回 **400**（`ADMIN_PERMISSIONS_IMPLICIT`）。因為只有 admin 能授權而 admin 又被擋在這裡，「自我提權」在結構上不可能發生。
- 權限**即時生效**：每請求查資料庫、不寫入 JWT。收回後，持有舊 token 的使用者下一個請求即被擋下。
- 必須記錄 `granted_by`／`granted_at`；授權人被刪除時 `granted_by` 轉 NULL、紀錄保留。
- 傳入空陣列代表**收回全部**；白名單以外的權限鍵回 **400**。
- 被授予 `exports.run` 的一般員工，匯出範圍**限縮在自己所屬部門**（與 manager 相同），未指派部門者回 403。

---

## 4. 核心功能模組

### 4.1 上下班打卡

#### 4.1.1 上班打卡

紀錄當前虛擬時鐘時間。系統比對「當日應到班時間」與「緩衝時間」自動判定 `normal` 或 `late`；**非工作日（週末或國定假日）打卡一律判定 `holiday_work`**，不適用遲到判定。

**判定邊界（以「分鐘」為粒度）**：設 `deadline = expected_start + grace_period_minutes`，打卡時間先截斷到分鐘再比較。`punch_in_time <= deadline` 判 `normal`，`>` 判 `late`。

> 例：09:00 + 10 分 → 09:10:00 與 09:10:59 皆為 `normal`，09:11:00 為 `late`。**判定粒度必須是分鐘，不能是秒**，否則同一個「9 點 10 分」會因秒數不同判成不同結果。

**`expected_start`（當日應到班時間）**：預設等於表定上班時間；若當日有已核准請假**從表定上班時間起連續涵蓋**（例如上午請假 09:00–12:00），則往後推到請假結束時間；若推完剛好落在表定午休區間內，再推到午休結束——半天假下午回來上班本就有一段午休銜接，不該被算成遲到。無請假時恆等於表定上班時間。

#### 4.1.2 到班偏移量（雙向緩衝）

正常工時結束時間、浮動午休窗、工時起算點三者**共用同一個偏移量**，值域固定為 `[−grace_period_minutes, +grace_period_minutes]`：

- 錨點預設為 `expected_start`。
- 若打卡時間已達**表定**午休開始（不是浮動後的午休，避免循環依賴），錨點改為 `max(expected_start, 表定午休結束)`，且下限收斂為 0——上午整段已經錯過，那不叫「提早到班」，不該倒給緩衝。
- 晚到為正值，午休與正常工時結束同步往後；早到為負值，同步往前。

#### 4.1.3 工時起算點

```
工時起算點 = max(實際打卡時間, expected_start + 到班偏移量)
```

偏移量非負時恆等於實際打卡時間（準點或遲到，行為不變）；只有「提早到班超過緩衝」時才被墊高——**提早超過緩衝的部分不計入工時**，要認列請走加班申請。

> 例：緩衝 10 分鐘、08:48 上班／12:48 下班 → 起算點墊高到 08:50，工時 3.00（不是把提早的 12 分鐘也算進去的 3.20）。

#### 4.1.4 正常工時結束時間

```
正常工時結束 = min(封頂式, 累積式)
```

- **封頂式** = 表定下班時間 + 到班偏移量
- **累積式** = 工時起算點 + 當日應工時 + 午休長度 −（當日已核准請假時數）

兩式取小的理由：只有封頂式，遲到者的正常工時結束會跟著無限往後（極晚到班會算到半夜）；只有累積式，輕微遲到者會被完整計滿 8 小時。

#### 4.1.5 浮動午休

午休區間隨到班偏移量同步平移（晚到則午休晚、早到則午休早），平移量同樣受緩衝上下限約束。**這是出勤打卡專用的規則，請假時數的午休不浮動**（見 §4.3）。

#### 4.1.6 下班打卡與工時

紀錄下班時間並計算當日工時（`NUMERIC(5,2)`，四捨五入至小數點後兩位）。工時 = `[工時起算點, min(下班時間, 正常工時結束)]` 區間長度扣除與浮動午休的重疊。

**下班打卡回應必須包含** `normal_work_end`、`late_punch_out_threshold`（= `normal_work_end + 1 小時`）、`overtime_eligible_start`、`is_workday`，供前端判斷是否跳出晚下班提示，前端不得自行推算時間。

#### 4.1.7 早退判定

```
早退 = 下班時間（截斷至分鐘） < 正常工時結束（截斷至分鐘）
```

**早退沒有任何寬限**。一天該做滿的工時（已把當天核准的請假、補打卡調整算進去）就是要做滿到那一刻——表定下班 18:00，即使 09:00 準時上班，17:55 打下班卡一樣算早退。

> 緩衝時間**只用在到班這一端**（遲到寬限、提早到班的工時起算），下班端不適用。這是刻意的不對稱，不是遺漏。

早退以獨立布林欄位 `is_early_leave` 表示，**不擴充 `status` 列舉值**——遲到與早退可以同時成立，塞進同一個欄位會互相覆蓋。

#### 4.1.8 缺勤自動標記

排程每 6 小時執行一次（啟動時亦立即執行一次），以虛擬時鐘的「今天」為基準回溯 60 天，對每位使用者、每個工作日，若完全無出勤列則補一筆 `status='absent'`（`ON CONFLICT DO NOTHING`）。

#### 4.1.9 並行打卡的一致性保證

同一使用者對同一日期的兩個並行上班（或下班）打卡請求，**恰好一個成功，另一個回 409**（`ALREADY_PUNCHED_IN` / `ALREADY_PUNCHED_OUT`），不得兩者皆成功、也不得回 500。

> **為何不能只靠「先查、有列就 UPDATE、沒有就 INSERT」**：這個決策橫跨兩個獨立的資料庫陳述式，中間有一段 `await` 的空檔——兩個並行請求的查詢都可能先看到「今天還沒有紀錄」，各自決定要走 INSERT；但真正寫入時，其中一個會因為對方已搶先提交而看到「有列了」，於是**改口走 UPDATE**，安靜覆蓋掉對方剛寫入的資料，`UNIQUE(user_id, punch_date)` 這道約束因此完全沒被觸發，兩邊都「成功」。跟 §4.6 場地借用的 TOCTOU 是同一類問題，但這裡連資料庫約束都救不了，因為競態發生在查詢決策本身，不是在最終寫入的那一刻。
>
> **修法**：寫入端必須用單一陳述式的 `INSERT ... ON CONFLICT (user_id, punch_date) DO UPDATE ... WHERE <該次操作要保護的欄位> IS NULL RETURNING ...`——PostgreSQL 保證同一時間只有一個交易能通過那個 `WHERE` guard，另一個會因為 `RETURNING` 不到列而明確知道自己該回 409，不存在「兩邊都以為自己合法寫入」的中間狀態。

### 4.2 出勤資料模型：純衍生

**`attendances` 只保存「原始打卡事實」**，補打卡與請假核准**不覆寫**這張表。異動後的「生效值」在**讀取時** join 已核准申請單即時算出，不落地。

- 生效欄位：`effective_punch_in_time`、`effective_punch_out_time`、`effective_status`、`effective_work_hours`、`effective_is_early_leave`。
- `is_adjusted`：已核准申請**真的改動了生效值**時為真。
- `has_changes`：當天存在**任何狀態**（待審／已核准／已駁回）的補打卡或請假申請即為真。與 `is_adjusted` 語意不同，不可合併——被駁回或待審核的申請也該讓使用者看得出「這天有動過」。
- `is_missing_punch_out`：工作日、有上班時間、無下班時間、且日期早於今天。

所有出勤讀取路徑（個人紀錄、全公司紀錄、今日狀態、匯出）**必須經過同一個生效值解析函式**，不得各自重算一套。

### 4.3 請假

- 假別：`事假`、`病假`、`特別休假`、`公假`。`特別休假` 以外的假別必填事由。
- 時數計算：**逐工作日**與工作時間窗取交集後加總，自動排除週末與國定假日。
- **工作時間窗套用緩衝**：`[work_start − grace, lunch_start]` 與 `[lunch_end, work_end + grace]`，但**只在整個請假區間真正的頭尾兩端套用**，多天請假的中間日維持表定時間。
  > 不限頭尾會讓「週五 09:00 到週一 18:00」這類剛好卡整點的多天請假被誤多算。
- **請假的午休固定不浮動**：請假通常事前申請、當天沒有打卡可據以浮動，硬要浮動只會讓基準比規則本身更難解釋。這是與 §4.1.5 刻意的差異。

#### 4.3.1 假別配額

純函式即時算出，不落地儲存。任何角色皆可查詢自己的配額。

- **特別休假**：依勞基法第 38 條，以**到職週年制**計算（滿 6 個月 3 日、1 年 7 日、2 年 10 日、3 年 14 日、5 年 15 日；滿 10 年起每滿 1 年加給 1 日，即滿 10 年 16 日、滿 11 年 17 日……滿 24 年達到 30 日上限，之後不再增加）。
- **事假**（14 日）、**病假**（30 日）：依**曆年制**計算。
- **公假**：不限額度。

### 4.4 加班

- 時數以 **30 分鐘為單位**捨去，不足 30 分鐘不計入；未滿 0.5 小時直接回 400。
- 計算時**先扣除與表定午休的重疊**再捨去（假日出勤橫跨午休的加班不得把休息時間算進去）。
- **起算點防呆**：加班開始時間不得早於 `overtime_eligible_start`。
  - 工作日：`正常工時結束 + 30 分鐘休息`
  - 非工作日：實際上班打卡時間（**截斷至分鐘**）
- 當天若有**待審核**的請假或補打卡申請，不得送出加班申請（先審完再申請，避免時數基準在審核後改變）。

### 4.5 申請單與審核

三種申請單（補打卡／請假／加班）共用同一套審核狀態機：`pending` → `approved`／`rejected`。

- 補打卡：同一天已有 `pending` 或 `approved` 的補打卡申請時，拒絕新增（409）。
- 補打卡目標日期**不得為未來日期**（以虛擬時鐘的營業日判斷）。
- 駁回時**必須**填寫審核備註。
- 已審核的申請不得重複審核（409）。
- 審核時間取自虛擬時鐘，且必須保證 `created_at < reviewed_at`。

### 4.6 場地借用

**兩層防護**，缺一不可：

1. **應用層預檢**：SELECT 查詢時段是否重疊，回傳含衝突時段與預約人姓名的友善訊息（409）。
2. **資料庫層排除約束**：`EXCLUDE USING gist (room_id WITH =, tstzrange(start_time, end_time, '[)') WITH &&) WHERE (status = 'confirmed')`。

> **為何兩層都要（TOCTOU）**：只有應用層預檢時，兩個並行請求可能同時通過檢查（此時都還沒 INSERT），然後兩者都寫入成功——這是典型的 Time-Of-Check to Time-Of-Use 競態。反過來只靠資料庫約束，使用者只會收到 PostgreSQL 內部格式的錯誤。兩層各司其職：一層給人看，一層給機器保證。錯誤處理器須把 `23P01` 轉譯為 409。

- 區間用**半開區間 `[)`**：09:00–11:00 與 11:00–12:00 **首尾相接不算衝突**。
- 預約不得跨日。
- 取消：僅本人可取消自己的預約；`admin` 可強制釋放任何預約。

### 4.7 員工與部門

- `GET /api/users` 開放**任何已登入角色**查詢全公司清單（通訊錄用途，含分機號碼），支援 `department_id` 篩選。建立、修改、刪除僅限 `admin`。
- `PUT /api/users/{id}` 的 `extension_number`／`hire_date` 未傳入時**必須用 `COALESCE` 保留原值**，不得覆蓋為 NULL。
- 員工編號由資料庫序列產生（`EMP{年}{3碼}`），**不接受前端傳入**。
- 部門主管必須具備 `manager` 或 `admin` 角色（400 `INVALID_MANAGER_ROLE`）。
- 刪除部門時成員的 `department_id` 由外鍵 `ON DELETE SET NULL` 處理。
- 不得刪除自己的帳號（400 `CANNOT_DELETE_SELF`）。

### 4.8 匯出報表

五種資料類型：`employees`、`attendance`（生效值）、`attendance-raw`（原始打卡）、`attendance-changes`（異動紀錄）、`room-bookings`。

- 支援欄位勾選與部門／員工／日期區間篩選，格式為 `.xlsx`。
- **範圍限縮 deny-by-default**：非 `admin` 一律強制注入請求者的 `department_id`（覆蓋前端傳來的值），`room-bookings` 類型除外。請求者未指派部門時回 403。
- 指定他部門成員的 `user_id` 時回 403。

### 4.9 國定假日

- `holidays` 表由 `admin` 或持有 `holidays.manage` 權限者維護。
- `GET /api/holidays` 任何角色皆可查詢（首頁與假別頁的行事曆需要）。
- 政府年度行事曆需每年公告，系統**不自動抓取**，由管理者於年初手動維護。

### 4.10 展示用虛擬時鐘

- `demo_clock` 表保存 `real_anchor` 與 `virtual_anchor` 單列。
- `get_virtual_now() = clamp(virtual_anchor + (真實現在 − real_anchor), 2026-08-24, 2026-08-31)`——虛擬時鐘會**跟著真實時間持續走動**，不是停在設定的那一刻。
- `GET`／`PUT /api/demo/clock` 開放**任何登入角色**調整，超出範圍自動 clamp 回邊界而非報錯。
- 前端顯示必須每秒本地推算並定期（60 秒）向後端校正，否則畫面時間會與實際打卡時間不一致。

### 4.11 展示資料重置

- `POST /api/demo/reset`（僅 admin）：清空全部業務資料表並重新載入種子資料，回傳各表筆數摘要。
- 正式環境（`NODE_ENV=production`）另有閒置自動重置排程，閒置門檻 `DEMO_RESET_IDLE_MINUTES`（預設 15 分鐘，設為 0 可關閉）。
- **閒置計時器刻意使用真實時間**（`time.monotonic()`），不用虛擬時鐘——虛擬時間到達 clamp 上限後不再前進，用它會讓重置機制永遠不觸發。
- 種子腳本開頭即 `TRUNCATE ... RESTART IDENTITY CASCADE`，因此可重複執行。

---

## 5. 資料庫模型

全表使用 `TIMESTAMPTZ`（不用 `TIMESTAMP`）。共用觸發器函式 `set_updated_at()`；`btree_gist` extension 供排除約束使用。

### 5.1 departments

| 欄位 | 型別 | 約束 |
| :--- | :--- | :--- |
| id | SERIAL | PK |
| name | VARCHAR(100) | NOT NULL |
| manager_id | INTEGER | FK → users(id) ON DELETE SET NULL |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

觸發器：`trg_departments_updated_at`

### 5.2 users

| 欄位 | 型別 | 約束 |
| :--- | :--- | :--- |
| id | SERIAL | PK |
| name | VARCHAR(100) | NOT NULL |
| email | VARCHAR(255) | NOT NULL UNIQUE |
| password_hash | VARCHAR(255) | NOT NULL |
| role | VARCHAR(20) | NOT NULL, CHECK IN ('admin','manager','employee') |
| department_id | INTEGER | FK → departments(id) ON DELETE SET NULL |
| is_first_login | BOOLEAN | NOT NULL DEFAULT true |
| hire_date | DATE | NOT NULL DEFAULT CURRENT_DATE |
| extension_number | VARCHAR(20) | |
| employee_no | VARCHAR(20) | UNIQUE INDEX WHERE employee_no IS NOT NULL |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

輔助：`employee_no_seq` SEQUENCE。觸發器：`trg_users_updated_at`

### 5.3 user_permissions

| 欄位 | 型別 | 約束 |
| :--- | :--- | :--- |
| user_id | INTEGER | NOT NULL, FK → users(id) **ON DELETE CASCADE** |
| permission | VARCHAR(50) | NOT NULL, CHECK IN ('holidays.manage','settings.manage','exports.run') |
| granted_by | INTEGER | FK → users(id) **ON DELETE SET NULL** |
| granted_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

PK `(user_id, permission)`（已提供 user_id 前導索引，不需另建）。無 `id`、無 `updated_at`、無觸發器——授權只有 INSERT／DELETE，沒有 UPDATE 語意。

> CHECK 白名單必須用「先 `DROP CONSTRAINT IF EXISTS` 再 `ADD CONSTRAINT`」的寫法，不能寫在 `CREATE TABLE IF NOT EXISTS` 裡面——表已存在時整段會被跳過，日後擴充權限鍵改這支檔案不會生效。

### 5.4 system_settings（恆單列）

| 欄位 | 型別 | 約束 |
| :--- | :--- | :--- |
| id | INTEGER | PK, DEFAULT 1, **CHECK (id = 1)** |
| work_start_time | TIME | NOT NULL DEFAULT '09:00' |
| work_end_time | TIME | NOT NULL DEFAULT '18:00' |
| lunch_start_time | TIME | NOT NULL DEFAULT '12:00' |
| lunch_end_time | TIME | NOT NULL DEFAULT '13:00' |
| grace_period_minutes | INTEGER | NOT NULL DEFAULT 10, CHECK 0–240 |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

觸發器：`trg_system_settings_updated_at`

### 5.5 attendances

| 欄位 | 型別 | 約束 |
| :--- | :--- | :--- |
| id | SERIAL | PK |
| user_id | INTEGER | NOT NULL, FK → users(id) ON DELETE CASCADE |
| punch_date | DATE | NOT NULL |
| punch_in_time / punch_out_time | TIMESTAMPTZ | |
| status | VARCHAR(20) | NOT NULL DEFAULT 'normal', CHECK IN ('normal','late','absent','holiday_work','on_leave') |
| work_hours | NUMERIC(5,2) | |
| is_early_leave | BOOLEAN | NOT NULL DEFAULT false |
| note | TEXT | |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

UNIQUE `(user_id, punch_date)`；索引 `(user_id, punch_date DESC)`。

> **本表刻意不掛 `updated_at` 觸發器**：觸發器內部呼叫 SQL 的 `now()`，不知道虛擬時鐘的偏移量，會造成「打卡時間是虛擬過去、`updated_at` 卻是真實現在」的不一致。時間一律由應用層帶入 `get_virtual_now()` 的值。

### 5.6 punch_requests

| 欄位 | 型別 | 約束 |
| :--- | :--- | :--- |
| id | SERIAL | PK |
| user_id | INTEGER | NOT NULL, FK → users(id) ON DELETE CASCADE |
| target_date | DATE | NOT NULL |
| type | VARCHAR(10) | NOT NULL, CHECK IN ('in','out','both') |
| requested_in_time / requested_out_time | TIMESTAMPTZ | |
| reason | TEXT | NOT NULL |
| status | VARCHAR(20) | NOT NULL DEFAULT 'pending', CHECK IN ('pending','approved','rejected') |
| reviewer_id | INTEGER | FK → users(id) ON DELETE SET NULL |
| review_note | TEXT | |
| reviewed_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

索引：`(status, user_id)`、`(reviewer_id)`

### 5.7 leave_requests

同 5.6 結構，另有 `leave_type VARCHAR(20) NOT NULL CHECK IN ('事假','病假','特別休假','公假')`，並以 `start_time`／`end_time`／`hours NUMERIC(5,2) NOT NULL` 取代 `target_date`／`type`／`requested_*`。

### 5.8 overtime_requests

同 5.7 結構但無 `leave_type`。

### 5.9 rooms

`id SERIAL PK`、`name VARCHAR(100) NOT NULL`、`capacity INTEGER NOT NULL`、`location_info VARCHAR(255)`、`created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### 5.10 room_bookings

| 欄位 | 型別 | 約束 |
| :--- | :--- | :--- |
| id | SERIAL | PK |
| room_id | INTEGER | NOT NULL, FK → rooms(id) ON DELETE CASCADE |
| user_id | INTEGER | NOT NULL, FK → users(id) ON DELETE CASCADE |
| title | VARCHAR(255) | NOT NULL |
| start_time / end_time | TIMESTAMPTZ | NOT NULL |
| status | VARCHAR(20) | NOT NULL DEFAULT 'confirmed', CHECK IN ('confirmed','cancelled') |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

**排除約束** `no_double_booking`：`EXCLUDE USING gist (room_id WITH =, tstzrange(start_time, end_time, '[)') WITH &&) WHERE (status = 'confirmed')`
索引：`(room_id, start_time)`。觸發器：`trg_room_bookings_updated_at`

### 5.11 holidays

`holiday_date DATE PK`、`name VARCHAR(100) NOT NULL`、`created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### 5.12 demo_clock（恆單列）

`id INTEGER PK DEFAULT 1 CHECK (id = 1)`、`real_anchor TIMESTAMPTZ NOT NULL`、`virtual_anchor TIMESTAMPTZ NOT NULL`、`updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

---

## 6. API 契約

全部端點以 `/api` 為前綴。權限欄位標示為「登入」代表任何已登入角色皆可。

### 6.1 認證

| Method | 路徑 | 權限 | 請求 | 回應 |
| :--- | :--- | :--- | :--- | :--- |
| POST | `/auth/login` | 公開 | `email`、`password` | `{token, user}` |
| GET | `/auth/me` | 登入 | — | `{user}` |
| POST | `/auth/change-password` | 登入 | `oldPassword`、`newPassword`（≥8 碼且需同時含英文字母與數字） | `{user}` |

`user` 物件：`{id, name, email, role, department_id, is_first_login, permissions}`

### 6.2 出勤

| Method | 路徑 | 權限 | 說明 |
| :--- | :--- | :--- | :--- |
| POST | `/attendance/punch-in` | 登入 | 對象取自 token，不解析請求中的任何 user_id |
| POST | `/attendance/punch-out` | 登入 | 回應含 `normal_work_end`、`late_punch_out_threshold`、`overtime_eligible_start`、`is_workday` |
| GET | `/attendance/today` | 登入 | |
| POST | `/attendance/today/note` | 登入 | 無請求主體，伺服器端寫入固定文字「處理私人事務」 |
| GET | `/attendance/me` | 登入 | query：`start_date`、`end_date`、`status`、`page`、`page_size`(1–100) |
| GET | `/attendance` | admin | query：`user_id`、`department_id`、`start_date`、`end_date`、`status` |
| GET | `/attendance/changes` | 登入 | 範圍控管在 service：本人／manager 限同部門／admin 不限 |

`status` 允許值：`normal`、`late`、`absent`、`holiday_work`、`on_leave`、`early_leave`、`missing_punch_out`。
篩選 `normal` 時**必須同時排除**早退與未打下班卡的日子。

### 6.3 申請單

| Method | 路徑 | 權限 |
| :--- | :--- | :--- |
| POST | `/punch-requests`、`/leave-requests`、`/overtime-requests` | 登入 |
| GET | `/{type}-requests/me` | 登入（query `status`） |
| GET | `/{type}-requests/pending` | manager, admin |
| PATCH | `/{type}-requests/{id}/review` | manager, admin（body：`action` = approve/reject、`review_note`） |

### 6.4 場地

| Method | 路徑 | 權限 |
| :--- | :--- | :--- |
| GET | `/rooms` | 登入 |
| POST | `/room-bookings` | 登入 |
| GET | `/room-bookings` | 登入（query `date` 必填、`room_id`、`status`） |
| PATCH | `/room-bookings/{id}/cancel` | 登入（僅本人） |
| DELETE | `/room-bookings/{id}` | admin（強制釋放） |

### 6.5 員工、部門、權限

| Method | 路徑 | 權限 |
| :--- | :--- | :--- |
| GET | `/users` | 登入（query `department_id`） |
| POST / PUT / DELETE | `/users`、`/users/{id}` | admin |
| **GET** | **`/users/permissions`** | **admin**（回傳全部授權紀錄，供清單頁一次取回） |
| **PUT** | **`/users/{id}/permissions`** | **admin**（body：`permissions` 字串陣列，整組取代） |
| GET | `/departments` | admin, manager |
| POST / PUT / DELETE | `/departments`、`/departments/{id}` | admin |

> `GET /users/permissions` 的路由**必須定義在 `PUT /users/{user_id}` 之前**，避免靜態路徑被動態路徑搶匹配。

### 6.6 設定、假日、配額

| Method | 路徑 | 權限 |
| :--- | :--- | :--- |
| GET | `/settings` | 登入 |
| PUT | `/settings` | **`require_permission("settings.manage")`** |
| GET | `/holidays` | 登入 |
| POST | `/holidays` | **`require_permission("holidays.manage")`** |
| DELETE | `/holidays/{date}` | **`require_permission("holidays.manage")`**（回 204） |
| GET | `/leave-quota/me` | 登入 |

`PUT /settings` 驗證：四個時間欄位皆 `HH:mm` 格式，且必須滿足 `work_start < lunch_start < lunch_end < work_end`；`grace_period_minutes` 為 0–240 的整數。

### 6.7 匯出、展示、系統

| Method | 路徑 | 權限 |
| :--- | :--- | :--- |
| POST | `/exports/{kind}` | **`require_permission("exports.run", roles=("admin","manager"))`** |
| POST | `/demo/reset` | admin |
| GET / PUT | `/demo/clock` | 登入 |
| GET | `/admin/schema`、`/admin/schema/{table}/rows` | admin |
| GET | `/health` | 公開 |

> 匯出端點的 `roles` 參數**絕對不能省略**，寫成 `require_permission("exports.run")` 會套用預設的 `roles=("admin",)`，直接砍掉現有 manager 的匯出權。

---

## 7. 錯誤處理

統一格式：`{"error": {"message": "...", "code": "..."}}`

### 7.1 PostgreSQL 錯誤轉譯

| 例外 | HTTP | code | 訊息 |
| :--- | :--- | :--- | :--- |
| UniqueViolationError | 409 | `23505` | 資料已存在，違反唯一性限制。 |
| ExclusionViolationError | 409 | `23P01` | 此操作與既有資料衝突。 |
| ForeignKeyViolationError | 400 | `23503` | 關聯的資料不存在或不合法。 |
| 其他未捕例外 | 500 | — | 伺服器發生未預期的錯誤，請稍後再試。 |

### 7.2 業務錯誤碼

| Code | HTTP | 情境 |
| :--- | :--- | :--- |
| `UNAUTHORIZED` | 401 | 未帶或格式錯誤的 token |
| `INVALID_TOKEN` | 401 | token 無效或逾期 |
| `FORBIDDEN` | 403 | 角色／權限不足、跨部門審核、自審、非本人取消預約、匯出範圍越界 |
| `VALIDATION_ERROR` | 400 | 欄位驗證失敗 |
| `NOT_FOUND` | 404 | 申請單／使用者／部門／預約／場地／假日不存在 |
| `INVALID_CREDENTIALS` | 401 | 帳號或密碼錯誤（**不得區分兩者**） |
| `USER_NOT_FOUND` | 401 | token 對應的使用者已不存在 |
| `DEMO_ACCOUNT_PASSWORD_LOCKED` | 403 | 展示帳號密碼固定不可變更 |
| `INVALID_OLD_PASSWORD` | 401 | 舊密碼不正確 |
| `PASSWORD_UNCHANGED` | 400 | 新密碼與目前相同 |
| `ALREADY_PUNCHED_IN` | 409 | 今日已完成上班打卡 |
| `NOT_PUNCHED_IN` | 400 | 尚未上班打卡就要下班打卡 |
| `ALREADY_PUNCHED_OUT` | 409 | 今日已完成下班打卡 |
| `NO_ATTENDANCE_TODAY` | 400 | 今日無出勤列，無法標註備註 |
| `DUPLICATE_PUNCH_REQUEST` | 409 | 同日已有待審或已核准的補打卡申請 |
| `ALREADY_REVIEWED` | 409 | 申請單已被審核 |
| `OVERTIME_TOO_SHORT` | 400 | 加班時數不足 0.5 小時 |
| `PENDING_REQUEST_BLOCKS_OVERTIME` | 400 | 當天有待審申請 |
| `OVERTIME_STARTS_TOO_EARLY` | 400 | 加班起始早於可認列時間 |
| `BOOKING_CONFLICT` | 409 | 場地時段衝突（訊息含衝突時段與預約人） |
| `ALREADY_CANCELLED` | 409 | 預約已取消 |
| `HOLIDAY_ALREADY_EXISTS` | 409 | 該日已登記為國定假日 |
| `SINGLE_ADMIN_ONLY` | 400 | 系統僅允許一位管理者 |
| `LAST_ADMIN_PROTECTED` | 400 | 不得變更最後一位管理者的角色 |
| `CANNOT_DELETE_SELF` | 400 | 不得刪除自己的帳號 |
| `EMAIL_ALREADY_EXISTS` | 409 | 電子郵件重複 |
| `DEPARTMENT_NOT_FOUND` | 400 | 指定的部門不存在 |
| `INVALID_MANAGER_ROLE` | 400 | 部門主管須具備 manager 或 admin 角色 |
| **`ADMIN_PERMISSIONS_IMPLICIT`** | **400** | **不得對 admin 個別授予權限** |

---

## 8. 測試策略

| 層級 | 工具 | 涵蓋 |
| :--- | :--- | :--- |
| 後端整合 | pytest + httpx.AsyncClient + **真實 PostgreSQL** | API 契約、RBAC、SQL 正確性、錯誤碼。**主力防線** |
| 前端元件 | Vitest + Testing Library（**可 mock API 層**） | 表單驗證、角色守門、互動流程、響應式版面 |
| 端對端 | Playwright | 跨角色的完整業務流程 |

**不使用 mock 資料庫**：本專案的風險集中在 SQL 行為本身（UNIQUE 衝突、UPSERT 覆蓋語意、排除約束、時區轉換），mock 掉資料庫等於把要測的東西測掉了。測試資料庫必須與開發資料庫完全隔離，且執行破壞性操作前驗證資料庫名稱以 `_test` 結尾。

### 8.1 必測邊界

- **權限**：employee 打 admin 端點 403；manager 審跨部門單 403；manager 審自己的單 403（admin 豁免）；**未帶 token 回 401 而非 403**（驗證 authenticate 先於 authorize）。
- **細粒度權限**：同一個舊 token 在授權後立即可用、收回後立即被擋（釘住「權限不在 JWT 裡」）；只授予 A 權限者打 B 端點 403；被授予 `exports.run` 者匯出只拿得到自己部門資料；未指派部門者匯出 403；非 admin 打授權端點 403。
- **時間邊界**：`09:10:00` 與 `09:10:59` 皆判 `normal`、`09:11:00` 判 `late`；早退判定 `17:59:59` 為早退、`18:00:00` 不是。
- **區間重疊**：場地預約六種拓撲；首尾相接放行；兩筆並行請求只成功一筆。
- **請假時數**：跨週末與國定假日排除；緩衝窗只在頭尾兩端生效。
- **資料保留**：`PUT /users/{id}` 不傳 `extension_number` 時原值必須保留（`test_partial_update_preserves_extension_number`）。
- **稽核保留**：權限整組取代時，未變動的權限其 `granted_by`／`granted_at` 必須不變。
- **種子資料自洽**：全表掃描，每一筆 `attendances`／`leave_requests`／`overtime_requests` 都必須通過系統自身的業務規則重算。

### 8.2 非預設設定驗證

考勤相關的測試必須有一組以「08:30–17:30、緩衝 15 分、午休 12:30–13:30」跑同一套斷言，確保沒有任何寫死的時間字面值。
