import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import App from "./App";

vi.mock("./api/health.api", () => ({
  getHealth: vi.fn().mockResolvedValue({ status: "ok", database: "connected" }),
}));

test("顯示後端健康檢查結果", async () => {
  render(<App />);

  expect(await screen.findByText(/API 狀態：ok／資料庫：connected/)).toBeInTheDocument();
});
