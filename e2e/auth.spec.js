import { expect, test } from "@playwright/test";

test("未登入直接開受保護頁面會被導向登入頁", async ({ page }) => {
  await page.goto("/dashboard");

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Employee Portal" })).toBeVisible();
});

test("一鍵代入測試帳號可完成登入並進入首頁", async ({ page }) => {
  await page.goto("/login");

  await page.getByRole("button", { name: /一般員工 Employee/ }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: /陳小華，你好/ })).toBeVisible();
  // 側邊欄依角色過濾：一般員工看得到首頁與出勤紀錄。
  await expect(page.getByRole("link", { name: "出勤紀錄" })).toBeVisible();
});

test("登出後回到登入頁", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /一般員工 Employee/ }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("button", { name: "登出" }).click();

  await expect(page).toHaveURL(/\/login$/);
});
