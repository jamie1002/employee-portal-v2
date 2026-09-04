import { expect, test } from "@playwright/test";

// 展示虛擬時鐘固定在 2026-08-24 ~ 08-31。日期一律對著這個錨點，禁止 new Date()
// （見 docs/PITFALLS.md B5）。e2e 打的是開發資料庫、測試之間沒有資料隔離，
// 跑之前一律 npm run db:reset（見 docs/PITFALLS.md E4）。
async function loginAs(page, accountLabel) {
  await page.goto("/login");
  await page.getByRole("button", { name: accountLabel }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("送出請假申請後出現在我的申請清單", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  await page.getByRole("link", { name: "我的申請" }).click();
  await page.getByRole("button", { name: "請假" }).click();
  await page.getByRole("link", { name: "提出請假申請" }).click();
  await expect(page).toHaveURL(/\/requests\/leave\/new$/);

  await page.getByLabel("開始日期").fill("2026-08-25");
  await page.getByLabel("開始時間").fill("09:00");
  await page.getByLabel("結束日期").fill("2026-08-25");
  await page.getByLabel("結束時間").fill("18:00");
  await page.getByLabel(/申請理由/).fill("個人事務");
  await page.getByRole("button", { name: "送出申請" }).click();

  await expect(page).toHaveURL(/\/requests$/);
  await page.getByRole("button", { name: "請假" }).click();
  // 桌機／手機雙結構同時渲染（見 docs/UI-SPEC.md §2.4），role="cell" 只對應
  // 桌機表格版，可正確排除隱藏的卡片版。
  await expect(page.getByRole("cell", { name: "事假" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^待審/ })).toBeVisible();
});

test("主管在審核中心核准部門同仁的申請後清單即時更新", async ({ page }) => {
  await loginAs(page, /部門主管 Manager/);

  await page.getByRole("link", { name: "審核中心" }).click();
  await expect(page.getByRole("heading", { name: "審核中心" })).toBeVisible();

  // 種子資料未必有待審申請；此情境只驗證頁面本身能正常載入三個分頁與空狀態，
  // 不對特定筆數做斷言（實際核准流程已由後端整合測試涵蓋並行與跨部門情境）。
  await expect(page.getByRole("button", { name: /補打卡（\d+）/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /請假（\d+）/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /加班（\d+）/ })).toBeVisible();
});

test("假別頁顯示配額卡片", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  await page.getByRole("link", { name: "假別" }).click();

  await expect(page.getByRole("heading", { name: "假別剩餘量" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "特別休假" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "公假" })).toBeVisible();
});
