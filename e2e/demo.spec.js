import { expect, test } from "@playwright/test";

// e2e 打的是開發資料庫、測試之間沒有資料隔離，跑之前一律 npm run db:reset
// （見 docs/PITFALLS.md E4）。
//
// 這個檔案刻意不測「實際送出 PUT /demo/clock 調整到別的日期」或「真的點下確定
// 重置」——展示時鐘與展示資料是**全站共用的單一列**，不是每個瀏覽器分頁各自
// 獨立的狀態。這裡的 e2e 是 fullyParallel 執行、跟其他測試檔共用同一個開發
// 資料庫，真的呼叫這兩支 API 會讓其他同時在跑的測試（例如打卡、場地預約）
// 的資料在執行到一半時被沖掉。這兩條路徑改由後端測試
// （test_clock.py／test_demo_reset.py／test_seed_business_rules.py）與人工
// 瀏覽器驗證涵蓋，這裡只驗證安全、唯讀、不影響其他測試的 UI 行為。
async function loginAs(page, accountLabel) {
  await page.goto("/login");
  await page.getByRole("button", { name: accountLabel }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("標頭顯示展示時鐘且會持續走動，不是掛載時的死值", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  const clockText = page.getByText(/展示時間：/);
  await expect(clockText).toBeVisible();
  const first = await clockText.textContent();

  await expect.poll(async () => clockText.textContent(), { timeout: 5_000 }).not.toBe(first);
});

test("一般員工看不到重置展示資料按鈕", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  await expect(page.getByRole("button", { name: "重置展示資料" })).not.toBeVisible();
});

test("admin 可以看到重置按鈕，點擊後需要二次確認，取消不會觸發重置", async ({ page }) => {
  await loginAs(page, /管理者 Admin/);

  await page.getByRole("button", { name: "重置展示資料" }).click();
  await expect(page.getByRole("button", { name: "確定重置" })).toBeVisible();

  await page.getByRole("button", { name: "取消" }).click();

  await expect(page.getByRole("button", { name: "重置展示資料" })).toBeVisible();
  await expect(page.getByRole("button", { name: "確定重置" })).not.toBeVisible();
});
