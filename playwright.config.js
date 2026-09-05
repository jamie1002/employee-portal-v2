import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  // e2e 打的是同一份沒有交易隔離的開發資料庫（見 docs/PITFALLS.md E4）。
  // fullyParallel 會讓不同測試（甚至同一個 spec 檔裡的測試）被排進不同 worker
  // 同時打同一批固定 seed 帳號，互相干擾或在 CI 有限 CPU 下把回應拖過斷言逾時，
  // 造成間歇性失敗——舊版 employee-portal 已經因為同樣原因把 e2e 寫死成單一
  // worker 循序執行，這裡沿用同一個決策（見 docs/PITFALLS.md E6）。
  fullyParallel: false,
  workers: 1,
  // 刻意不設 retries：重跑一次只會撞到自己上一次留下的打卡紀錄（409），
  // 失敗照樣失敗還多花一倍時間。要能重試得等批 7 的展示資料重置 API 完成後，
  // 在 beforeEach 重置狀態。
  retries: 0,
  reporter: [["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "npm run dev:backend",
      url: "http://localhost:3000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "npm run dev:frontend",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
