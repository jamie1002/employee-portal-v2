import { expect, test } from "@playwright/test";

// 展示虛擬時鐘固定在 2026-08-24 ~ 08-31 這個視窗內。所有日期斷言一律對著這個
// 錨點，**禁止使用 new Date()**——真實日期會一直往前走，遲早超出視窗而讓測試
// 整批失效（見 docs/PITFALLS.md B5）。
const DEMO_WINDOW = /2026-08-\d{2}/;

// e2e 打的是開發資料庫，測試之間**沒有**資料隔離（跑之前一律 npm run db:reset，
// 見 docs/PITFALLS.md E4）。因此每個會改變狀態的測試各用一個展示帳號，
// 避免併行執行時互相把對方的卡打掉。
async function loginAs(page, accountLabel) {
  await page.goto("/login");
  await page.getByRole("button", { name: accountLabel }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

function todayStatusCard(page) {
  return page
    .locator(".glass-panel")
    .filter({ has: page.getByRole("heading", { name: "今日出勤狀態" }) });
}

test("首頁顯示虛擬時鐘的今天，而不是瀏覽器的今天", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  await expect(page.getByText(DEMO_WINDOW).first()).toBeVisible();
});

test("上班打卡後今日狀態卡即時更新", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  const punchInButton = page.getByRole("button", { name: "上班打卡" });
  await expect(punchInButton).toBeEnabled();
  await punchInButton.click();

  // 上班時間（第一個 <dd>）不再是「—」，且出現狀態徽章（落在緩衝內是正常、
  // 超過是遲到，兩者都代表判定確實跑起來了）。
  const card = todayStatusCard(page);
  await expect(card.getByRole("definition").first()).toHaveText(/^\d{2}:\d{2}$/);
  await expect(card.getByText(/正常|遲到/)).toBeVisible();

  await expect(punchInButton).toBeDisabled();
  await expect(page.getByRole("button", { name: "下班打卡" })).toBeEnabled();
});

test("下班打卡後工時以兩位小數呈現", async ({ page }) => {
  await loginAs(page, /部門主管 Manager/);

  await page.getByRole("button", { name: "上班打卡" }).click();
  const punchOutButton = page.getByRole("button", { name: "下班打卡" });
  await expect(punchOutButton).toBeEnabled();

  await punchOutButton.click();

  // 第三個 <dd> 是工時，格式固定兩位小數（生效值與資料庫值統一成同一種呈現）。
  await expect(todayStatusCard(page).getByRole("definition").nth(2)).toHaveText(/^\d+\.\d{2}$/);
  await expect(punchOutButton).toBeDisabled();
});

test("出勤紀錄頁可依狀態篩選", async ({ page }) => {
  await loginAs(page, /管理者 Admin/);
  await page.getByRole("link", { name: "出勤紀錄" }).click();

  await expect(page.getByRole("heading", { name: "出勤紀錄" })).toBeVisible();

  await page.getByLabel("狀態").selectOption("holiday_work");

  // holiday_work 只會出現在非工作日打卡，種子資料（近兩週劇本＋歷史回填）一律只
  // 產生工作日的出勤紀錄，任何帳號篩這個狀態都應該是空狀態，不是照舊列出全部。
  await expect(page.getByText("尚無出勤紀錄。")).toBeVisible();
});
