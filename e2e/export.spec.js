import { expect, test } from "@playwright/test";

// e2e 打的是開發資料庫、測試之間沒有資料隔離，跑之前一律 npm run db:reset
// （見 docs/PITFALLS.md E4）。
async function loginAs(page, accountLabel) {
  await page.goto("/login");
  await page.getByRole("button", { name: accountLabel }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("admin 可預覽並下載員工資料匯出", async ({ page }) => {
  await loginAs(page, /管理者 Admin/);

  await page.getByRole("link", { name: "匯出報表" }).click();
  await expect(page.getByRole("heading", { name: "匯出報表" })).toBeVisible();

  await page.getByRole("button", { name: "預覽" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("cell", { name: "陳小華" })).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下載 .xlsx" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("employees.xlsx");
});

test("manager 看不到部門篩選，提示文案不含「主管身分」", async ({ page }) => {
  await loginAs(page, /部門主管 Manager/);

  await page.getByRole("link", { name: "匯出報表" }).click();
  await expect(page.getByRole("heading", { name: "匯出報表" })).toBeVisible();

  await expect(page.getByRole("combobox", { name: "部門" })).not.toBeVisible();
  const hint = page.getByText(/僅能匯出所屬部門資料/);
  await expect(hint).toBeVisible();
  await expect(hint).not.toContainText("主管身分");
});

test("一般員工看不到匯出報表選單，直接連結會被 403 擋下", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  await expect(page.getByRole("link", { name: "匯出報表" })).not.toBeVisible();
});
