import { expect, test } from "@playwright/test";

// e2e 打的是開發資料庫、測試之間沒有資料隔離，跑之前一律 npm run db:reset
// （見 docs/PITFALLS.md E4）。日期固定用虛擬時鐘展示視窗以外的遠期日期
// （2099-06-15），跟種子資料與其他測試的預約完全不會撞在一起，比每個測試各挑
// 一個不同時段更省事。禁止用 new Date() 算日期（見 docs/PITFALLS.md B5）。
const BOOKING_DATE = "2099-06-15";

async function loginAs(page, accountLabel) {
  await page.goto("/login");
  await page.getByRole("button", { name: accountLabel }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

async function openVenuePage(page) {
  await page.getByRole("link", { name: "場地借用" }).click();
  await expect(page.getByRole("heading", { name: "場地借用" })).toBeVisible();
  await page.getByLabel("日期").fill(BOOKING_DATE);
}

async function submitBooking(page, { room, title, start, end }) {
  await page.getByRole("button", { name: "新增預約" }).click();
  await expect(page.getByRole("heading", { name: "新增預約" })).toBeVisible();
  await page.getByLabel("場地").selectOption({ label: room });
  await page.getByLabel("預約標題").fill(title);
  await page.getByLabel("開始時間").fill(start);
  await page.getByLabel("結束時間").fill(end);
  await page.getByRole("button", { name: "確認預約" }).click();
}

test("建立預約、偵測衝突、首尾相接放行、取消後可重新預約", async ({ page }) => {
  const responses = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/")) responses.push(response.status());
  });

  await loginAs(page, /一般員工 Employee/);
  await openVenuePage(page);

  await submitBooking(page, { room: "會議室 A", title: "部門會議", start: "09:00", end: "11:00" });
  await expect(page.getByRole("button", { name: /部門會議/ })).toBeVisible();

  // 衝突：10:00–12:00 與既有的 09:00–11:00 重疊。
  await submitBooking(page, { room: "會議室 A", title: "衝突會議", start: "10:00", end: "12:00" });
  const conflictMessage = page.getByText(/此時段與既有預約衝突/);
  await expect(conflictMessage).toBeVisible();
  await expect(conflictMessage).toContainText("09:00");
  await expect(conflictMessage).toContainText("11:00");
  await expect(conflictMessage).toContainText("陳小華");
  await page.getByRole("button", { name: "取消" }).click();

  // 首尾相接：11:00–12:00 緊接在既有預約之後，不算衝突，應該放行。
  await submitBooking(page, { room: "會議室 A", title: "緊接的會議", start: "11:00", end: "12:00" });
  await expect(page.getByRole("button", { name: /緊接的會議/ })).toBeVisible();

  // 取消原本第一筆預約後，同時段應可重新預約成功。
  await page.getByRole("button", { name: /部門會議/ }).click();
  await page.getByRole("button", { name: "取消預約" }).click();
  await expect(page.getByRole("button", { name: /部門會議/ })).not.toBeVisible();

  await submitBooking(page, { room: "會議室 A", title: "重新預約的會議", start: "09:00", end: "11:00" });
  await expect(page.getByRole("button", { name: /重新預約的會議/ })).toBeVisible();

  expect(responses.every((status) => status < 500)).toBe(true);
});

test("主管審核中心之外，admin 可強制釋放他人的場地預約", async ({ page }) => {
  await loginAs(page, /一般員工 Employee/);
  await openVenuePage(page);
  await submitBooking(page, { room: "會議室 B", title: "員工的會議", start: "13:00", end: "14:00" });
  await expect(page.getByRole("button", { name: /員工的會議/ })).toBeVisible();

  await page.getByRole("button", { name: "登出" }).click();
  await loginAs(page, /管理者 Admin/);
  await openVenuePage(page);

  await page.getByRole("button", { name: /員工的會議/ }).click();
  await expect(page.getByRole("button", { name: "強制釋放" })).toBeVisible();
  await expect(page.getByRole("button", { name: "取消預約" })).not.toBeVisible();
  await page.getByRole("button", { name: "強制釋放" }).click();

  await expect(page.getByRole("button", { name: /員工的會議/ })).not.toBeVisible();
});
