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
