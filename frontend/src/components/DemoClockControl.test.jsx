import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import DemoClockControl from "./DemoClockControl";

const mockSetDemoClock = vi.hoisted(() => vi.fn());
const mockGetDemoClock = vi.hoisted(() => vi.fn());
vi.mock("../api/demo.api", () => ({
  setDemoClock: (...args) => mockSetDemoClock(...args),
  getDemoClock: (...args) => mockGetDemoClock(...args),
}));

beforeEach(() => {
  mockSetDemoClock.mockReset();
  mockGetDemoClock.mockReset().mockResolvedValue({ virtual_now: "2026-08-24T01:00:00+00:00" });
  // jsdom 的 window.location.reload 不可直接 spyOn（唯讀屬性），改整個換掉。
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...window.location, reload: vi.fn() },
  });
});

test("未輸入時間時套用按鈕停用", () => {
  render(<DemoClockControl />);

  expect(screen.getByRole("button", { name: "套用" })).toBeDisabled();
});

test("輸入時間並套用會以台北時區組出 ISO 字串呼叫 setDemoClock，成功後重新整理頁面", async () => {
  mockSetDemoClock.mockResolvedValue({});
  render(<DemoClockControl />);

  fireEvent.change(screen.getByLabelText("調整展示時間"), { target: { value: "2026-08-26T10:00" } });
  fireEvent.click(screen.getByRole("button", { name: "套用" }));

  await waitFor(() => expect(mockSetDemoClock).toHaveBeenCalledWith("2026-08-26T10:00:00+08:00"));
  await waitFor(() => expect(window.location.reload).toHaveBeenCalled());
});

test("取得展示時間後自動帶入欄位並啟用套用按鈕，不會用瀏覽器的真實現在時間", async () => {
  mockGetDemoClock.mockResolvedValue({ virtual_now: "2026-08-24T01:00:00+00:00" }); // 台北 09:00
  render(<DemoClockControl />);

  await waitFor(() => expect(screen.getByLabelText("調整展示時間")).toHaveValue("2026-08-24T09:00"));
  expect(screen.getByRole("button", { name: "套用" })).not.toBeDisabled();
});

test("套用失敗時顯示錯誤訊息，不重新整理頁面", async () => {
  mockSetDemoClock.mockRejectedValue({ response: { data: { error: { message: "超出範圍" } } } });
  render(<DemoClockControl />);

  fireEvent.change(screen.getByLabelText("調整展示時間"), { target: { value: "2026-08-26T10:00" } });
  fireEvent.click(screen.getByRole("button", { name: "套用" }));

  await waitFor(() => expect(screen.getByText("超出範圍")).toBeInTheDocument());
  expect(window.location.reload).not.toHaveBeenCalled();
});
