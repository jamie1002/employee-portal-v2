import { expect, test } from "@playwright/test";

// 只測降級路徑：CI 沒有設定 GOOGLE_API_KEY → /api/chat 回 503 CHAT_UNAVAILABLE，
// 這條路徑穩定可重現，且一次覆蓋路由、選單過濾、API 串接、錯誤轉譯四件事。
// happy path 刻意不進 e2e（依賴外部服務、慢、不穩），由 backend/eval 負責驗收。
//
// 本機若已經 npm run db:ingest 過語料（代表 .env 設定了 GOOGLE_API_KEY），這條測試
// 會走 happy path 而不是預期的降級訊息，因此在測試開頭用 /api/health 的
// policy_chunk_count 欄位偵測並條件 skip（見 openspec/changes/add-policy-chat/design.md
// 風險 7：這個欄位本來就是為了「一眼看出語料灌了沒」而加的）。
test("AI 助理在未設定金鑰時顯示降級訊息", async ({ page, request }) => {
  const health = await request.get("http://localhost:3000/api/health");
  const body = await health.json();
  test.skip(
    Boolean(body.policy_chunk_count),
    "本機已 ingest 語料（已設定 GOOGLE_API_KEY），會走 happy path，跳過降級路徑測試",
  );

  await page.goto("/login");
  await page.getByRole("button", { name: /一般員工 Employee/ }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByTestId("app-sidebar").getByRole("link", { name: "AI 助理", exact: true }).click();
  await expect(page).toHaveURL(/\/chat$/);

  await page
    .getByPlaceholder("輸入你的問題，Enter 送出、Shift+Enter 換行")
    .fill("特別休假怎麼算？");
  await page.getByRole("button", { name: "送出" }).click();

  await expect(page.getByText("AI 助理目前無法使用（可能是展示環境尚未設定金鑰或語料），請稍後再試。")).toBeVisible();
});

// 依角色顯示不同建議問題：純前端行為，不呼叫 Gemini，所以不受上面那條
// 「happy path 不進 e2e」的限制。這一層要驗的是「真實登入 + 真實角色」串起來的
// 結果，前端單元測試 mock 掉 AuthContext 驗不到這一段。
async function openChatAs(page, accountLabel) {
  await page.goto("/login");
  await page.getByRole("button", { name: accountLabel }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByTestId("app-sidebar").getByRole("link", { name: "AI 助理", exact: true }).click();
  await expect(page).toHaveURL(/\/chat$/);
}

test("建議問題依角色切換，員工看不到團隊範圍的題目", async ({ page }) => {
  await openChatAs(page, /一般員工 Employee/);

  await expect(page.getByRole("button", { name: "我今天打卡了嗎？" })).toBeVisible();
  // 列出一個他沒有權限問的問題，點下去只會得到「你沒有權限」，是自找的挫折。
  await expect(page.getByRole("button", { name: /誰遲到最多/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /等我審核/ })).toHaveCount(0);

  // 批 A 埋的免責伏筆已拆除。
  await expect(page.getByText(/請至對應功能頁查詢/)).toHaveCount(0);
});

test("主管與管理員各自看到對應範圍的建議問題", async ({ page }) => {
  await openChatAs(page, /部門主管 Manager/);
  await expect(page.getByRole("button", { name: "我部門這個月誰遲到最多？" })).toBeVisible();
  await expect(page.getByRole("button", { name: /全公司誰缺勤最多/ })).toHaveCount(0);

  await page.getByRole("button", { name: "登出" }).click();

  await openChatAs(page, /管理者 Admin/);
  await expect(page.getByRole("button", { name: "這個月全公司誰缺勤最多？" })).toBeVisible();
  await expect(page.getByRole("button", { name: /我部門這個月/ })).toHaveCount(0);
});
