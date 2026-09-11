import { expect, test } from "@playwright/test";

// e2e 打的是開發資料庫、測試之間沒有資料隔離，跑之前一律 npm run db:reset
// （見 docs/PITFALLS.md E4）。
async function loginAs(page, accountLabel) {
  await page.goto("/login");
  await page.getByRole("button", { name: accountLabel }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("一般員工進入員工資訊頁不會因為 GET /departments 回 403 而整頁空白", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);

  await page.getByRole("link", { name: "員工資訊" }).click();

  await expect(page.getByRole("heading", { name: "員工資訊" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "陳小華" })).toBeVisible();
  // 一般員工看不到額外權限欄與建立表單。
  await expect(page.getByText("額外權限")).not.toBeVisible();
});

test("admin 建立部門、國定假日、修改考勤設定，並授予權限後該員工立即看到對應選單", async ({ page }) => {
  await loginAs(page, /管理者 Admin/);

  // 部門管理：建立一個新部門。
  await page.getByRole("link", { name: "部門管理" }).click();
  await expect(page.getByRole("heading", { name: "部門管理" })).toBeVisible();
  await page.getByLabel("部門名稱").fill("行銷部");
  await page.getByRole("button", { name: "建立部門" }).click();
  // 桌機／手機雙結構同時渲染（見 docs/UI-SPEC.md §2.4），role="cell" 只會對應
  // 桌機表格版（卡片版是 <div>，不掛 cell 角色），可正確排除隱藏的那一份。
  await expect(page.getByRole("cell", { name: "行銷部" })).toBeVisible();

  // 國定假日：新增一筆。
  await page.getByRole("link", { name: "國定假日" }).click();
  await page.getByLabel("日期").fill("2026-12-25");
  await page.getByLabel("名稱").fill("聖誕節（示範）");
  await page.getByRole("button", { name: "新增假日" }).click();
  await expect(page.getByRole("cell", { name: "聖誕節（示範）" })).toBeVisible();

  // 考勤設定：調整緩衝時間並確認成功訊息。
  await page.getByRole("link", { name: "考勤設定" }).click();
  await page.getByLabel("緩衝時間（分鐘）").fill("15");
  await page.getByRole("button", { name: "儲存設定" }).click();
  await expect(page.getByText("設定已更新")).toBeVisible();

  // 員工資訊頁：授予「陳小華」國定假日管理權限。
  await page.getByRole("link", { name: "員工資訊" }).click();
  const employeeRow = page.getByRole("row", { name: /陳小華/ });
  await employeeRow.getByRole("button", { name: "編輯" }).click();
  await page.getByRole("button", { name: "權限" }).click();
  await page.getByLabel("國定假日管理").check();
  await page.getByRole("button", { name: "完成" }).click();
  await page.getByRole("button", { name: "儲存" }).click();
  await expect(employeeRow.getByText("國定假日")).toBeVisible();

  await page.getByRole("button", { name: "登出" }).click();
  await loginAs(page, /一般員工 Employee/);

  // 重新整理即看到「國定假日」選單（權限即時生效，不寫進 JWT）。
  await expect(page.getByRole("link", { name: "國定假日" })).toBeVisible();
  await page.getByRole("link", { name: "國定假日" }).click();
  await expect(page.getByRole("heading", { name: "國定假日" })).toBeVisible();
});

test("資料庫管理頁可切換資料表與檢視結構定義", async ({ page }) => {
  await loginAs(page, /管理者 Admin/);

  await page.getByRole("link", { name: "資料庫管理" }).click();
  await expect(page.getByRole("heading", { name: "資料庫管理" })).toBeVisible();

  await page.getByLabel("資料表").selectOption("users");
  await expect(page.getByLabel("資料表")).toHaveValue("users");
  await page.getByRole("button", { name: "結構定義" }).click();
  await expect(page.getByRole("cell", { name: "email" })).toBeVisible();
});

test("主管只看得到所屬部門的出勤，員工完全沒有這個入口", async ({ page }) => {
  await loginAs(page, /部門主管 Manager/);

  // 文案依角色切換：主管看到的不是全公司。
  await expect(page.getByRole("link", { name: "部門出勤" })).toBeVisible();
  await expect(page.getByRole("link", { name: "全公司出勤" })).toHaveCount(0);

  await page.getByRole("link", { name: "部門出勤" }).click();
  await expect(page.getByRole("heading", { name: "部門出勤" })).toBeVisible();

  // 部門欄位是唯讀標籤，不是可切換的下拉——主管不能改成別的部門。
  await expect(page.getByLabel("部門")).toHaveText("研發部");

  // 表格只出現同部門成員；業務部的張大同不得出現。
  await expect(page.getByRole("cell", { name: "陳小華" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "張大同" })).toHaveCount(0);

  await page.getByRole("button", { name: "登出" }).click();
  await loginAs(page, /一般員工 Employee/);

  await expect(page.getByRole("link", { name: "部門出勤" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "全公司出勤" })).toHaveCount(0);

  // 直接輸入網址也不渲染任何出勤內容（RoleGate 回 null）。
  await page.goto("/admin/attendance");
  await expect(page.getByRole("heading", { name: "部門出勤" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "全公司出勤" })).toHaveCount(0);
});
