import { expect, test } from "@playwright/test";

// 批 8：全站響應式適配（docs/UI-SPEC.md §2）。驗收基準寬度 375px，
// 任何頁面都不得出現整頁水平捲軸（表格／時間軸容器內部的水平捲動允許）。
// 展示虛擬時鐘固定在 2026-08-24 ~ 08-31，日期一律對著這個錨點，禁止 new Date()
// （見 docs/PITFALLS.md B5）。e2e 打的是開發資料庫、測試之間沒有資料隔離，
// 跑之前一律 npm run db:reset（見 docs/PITFALLS.md E4）。
test.use({ viewport: { width: 375, height: 812 } });

async function loginAs(page, accountLabel) {
  await page.goto("/login");
  await page.getByRole("button", { name: accountLabel }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

// 手機版側邊欄是抽屜，預設收在畫面外（-translate-x-full），選單連結要先開
// 抽屜才點得到——直接點會因為元素還在視窗外而失敗，這正是要驗證的手機行為。
async function openDrawer(page) {
  await page.getByRole("button", { name: "開啟選單" }).click();
}

// 部分頁面內文另有同名或包含相同子字串的連結（如首頁的「查看我的申請」），
// 一律 scope 進側邊欄本體，並用 exact 比對，避免撞到頁面內容裡的連結。
async function clickNavLink(page, label) {
  await page.getByTestId("app-sidebar").getByRole("link", { name: label, exact: true }).click();
}

function hasNoPageHorizontalScroll(page) {
  return page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  );
}

test("漢堡按鈕可開關抽屜式側邊欄，點遮罩後關閉", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  const sidebar = page.getByTestId("app-sidebar");
  await expect(sidebar).toHaveAttribute("data-state", "closed");

  await openDrawer(page);
  await expect(sidebar).toHaveAttribute("data-state", "open");

  await page.getByTestId("drawer-backdrop").click();
  await expect(sidebar).toHaveAttribute("data-state", "closed");
});

test("375px 寬度下主要頁面都沒有整頁水平捲軸", async ({ page }) => {
  await loginAs(page, /管理者 Admin/);
  expect(await hasNoPageHorizontalScroll(page)).toBe(true);

  await openDrawer(page);
  await clickNavLink(page, "出勤紀錄");
  await expect(page.getByRole("heading", { name: "出勤紀錄" })).toBeVisible();
  expect(await hasNoPageHorizontalScroll(page)).toBe(true);

  await openDrawer(page);
  await clickNavLink(page, "我的申請");
  await expect(page.getByRole("heading", { name: "我的申請" })).toBeVisible();
  expect(await hasNoPageHorizontalScroll(page)).toBe(true);

  await openDrawer(page);
  await clickNavLink(page, "場地借用");
  await expect(page.getByRole("heading", { name: "場地借用" })).toBeVisible();
  // 手機版時間軸捲動提示應可見（sm:hidden，375px 屬於手機斷點）。
  await expect(page.getByText("← 左右滑動查看場地時段 →")).toBeVisible();
  expect(await hasNoPageHorizontalScroll(page)).toBe(true);

  await openDrawer(page);
  await clickNavLink(page, "員工資訊");
  await expect(page.getByRole("heading", { name: "員工資訊" })).toBeVisible();
  expect(await hasNoPageHorizontalScroll(page)).toBe(true);
});

test("手機版可完整送出一筆補打卡申請", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  await openDrawer(page);
  await clickNavLink(page, "我的申請");
  await page.getByRole("link", { name: "提出補打卡申請" }).click();
  await expect(page).toHaveURL(/\/requests\/punch\/new$/);

  // 補打卡不得為未來日期（相對虛擬時鐘錨點 2026-08-24），選一個明確在過去、
  // 且不撞種子資料既有補打卡申請（08-18／08-21）的日期。
  await page.getByLabel("日期").fill("2026-08-20");
  await page.getByLabel("上班時間").fill("09:00");
  await page.getByLabel(/申請理由/).fill("忘記打卡");
  await page.getByRole("button", { name: "送出申請" }).click();

  await expect(page).toHaveURL(/\/requests$/);
});

test("375px 寬度下主管的部門出勤頁不出現整頁水平捲軸", async ({ page }) => {
  await loginAs(page, /部門主管 Manager/);

  await openDrawer(page);
  await clickNavLink(page, "部門出勤");
  await expect(page.getByRole("heading", { name: "部門出勤" })).toBeVisible();
  // 唯讀的部門標籤與其餘篩選欄位一樣是 w-full，手機斷點下各自佔滿整行。
  await expect(page.getByLabel("部門")).toHaveText("研發部");
  expect(await hasNoPageHorizontalScroll(page)).toBe(true);
});
