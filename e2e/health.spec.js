import { expect, test } from "@playwright/test";

test("首頁載入且能連上後端健康檢查", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/API 狀態：ok／資料庫：connected/)).toBeVisible();
});
