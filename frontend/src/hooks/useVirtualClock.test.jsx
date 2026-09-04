import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { useVirtualClock } from "./useVirtualClock";

const mockGetDemoClock = vi.hoisted(() => vi.fn());
vi.mock("../api/demo.api", () => ({
  getDemoClock: (...args) => mockGetDemoClock(...args),
}));

function Probe() {
  const virtualNow = useVirtualClock();
  return <span data-testid="now">{virtualNow ? virtualNow.toISOString() : "none"}</span>;
}

beforeEach(() => {
  // shouldAdvanceTime：讓 testing-library 的 waitFor 內部輪詢（靠真實時間推進）
  // 能繼續運作，同時仍可用 vi.advanceTimersByTimeAsync() 手動快轉本測試要控制的計時器。
  vi.useFakeTimers({ shouldAdvanceTime: true });
  mockGetDemoClock.mockReset();
  mockGetDemoClock.mockResolvedValue({ virtual_now: "2026-08-24T01:00:00+00:00" });
});

afterEach(() => {
  vi.useRealTimers();
});

test("掛載時同步一次並顯示虛擬時間", async () => {
  render(<Probe />);

  await waitFor(() => expect(screen.getByTestId("now").textContent).not.toBe("none"));
  expect(mockGetDemoClock).toHaveBeenCalledTimes(1);
});

test("每秒本地推算前進，不重複呼叫 API", async () => {
  render(<Probe />);
  await waitFor(() => expect(screen.getByTestId("now").textContent).not.toBe("none"));
  const first = new Date(screen.getByTestId("now").textContent).getTime();

  await vi.advanceTimersByTimeAsync(5_000);

  const second = new Date(screen.getByTestId("now").textContent).getTime();
  expect(second - first).toBeGreaterThanOrEqual(4_000);
  expect(mockGetDemoClock).toHaveBeenCalledTimes(1);
});

test("60 秒後重新呼叫 API 校正", async () => {
  render(<Probe />);
  await waitFor(() => expect(mockGetDemoClock).toHaveBeenCalledTimes(1));

  await vi.advanceTimersByTimeAsync(60_000);

  expect(mockGetDemoClock).toHaveBeenCalledTimes(2);
});
