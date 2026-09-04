import { describe, expect, test } from "vitest";
import { formatTime, monthRangeOf, taipeiDateKey } from "./datetime";

describe("formatTime", () => {
  test("以台北時區顯示時分", () => {
    expect(formatTime("2026-08-24T01:00:00+00:00")).toBe("09:00");
  });

  test("沒有值時顯示破折號", () => {
    expect(formatTime(null)).toBe("—");
  });
});

describe("monthRangeOf", () => {
  test("由後端回傳的營業日推算當月起訖，不依賴瀏覽器的今天", () => {
    expect(monthRangeOf("2026-08-24")).toEqual({ startDate: "2026-08-01", endDate: "2026-08-31" });
  });

  test("正確處理小月與二月", () => {
    expect(monthRangeOf("2026-04-15").endDate).toBe("2026-04-30");
    expect(monthRangeOf("2026-02-10").endDate).toBe("2026-02-28");
  });
});

describe("taipeiDateKey", () => {
  test("UTC 深夜換算成台北的隔天", () => {
    expect(taipeiDateKey("2026-08-24T16:30:00+00:00")).toBe("2026-08-25");
  });
});
