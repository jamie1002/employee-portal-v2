import { estimateLeaveHours } from "./leaveHours";

const DEFAULT_SETTINGS = {
  work_start_time: "09:00:00",
  work_end_time: "18:00:00",
  lunch_start_time: "12:00:00",
  lunch_end_time: "13:00:00",
  grace_period_minutes: 10,
};

const OTHER_SETTINGS = {
  work_start_time: "08:30:00",
  work_end_time: "17:30:00",
  lunch_start_time: "12:30:00",
  lunch_end_time: "13:30:00",
  grace_period_minutes: 15,
};

test("輸入不完整時回傳 0", () => {
  expect(estimateLeaveHours({ settings: DEFAULT_SETTINGS })).toBe(0);
  expect(
    estimateLeaveHours({ startDate: "2026-08-24", startTime: "09:00", settings: DEFAULT_SETTINGS }),
  ).toBe(0);
});

test("結束時間不晚於開始時間時回傳 0", () => {
  expect(
    estimateLeaveHours({
      startDate: "2026-08-24", startTime: "18:00", endDate: "2026-08-24", endTime: "09:00",
      settings: DEFAULT_SETTINGS,
    }),
  ).toBe(0);
});

test("單日整天請假扣除午休為 8 小時", () => {
  expect(
    estimateLeaveHours({
      startDate: "2026-08-24", startTime: "09:00", endDate: "2026-08-24", endTime: "18:00",
      settings: DEFAULT_SETTINGS,
    }),
  ).toBe(8);
});

test("單日下午請假不跨午休", () => {
  expect(
    estimateLeaveHours({
      startDate: "2026-08-24", startTime: "13:00", endDate: "2026-08-24", endTime: "18:00",
      settings: DEFAULT_SETTINGS,
    }),
  ).toBe(5);
});

test("單日區間橫跨午休，午休不計入時數", () => {
  expect(
    estimateLeaveHours({
      startDate: "2026-08-24", startTime: "11:00", endDate: "2026-08-24", endTime: "14:00",
      settings: DEFAULT_SETTINGS,
    }),
  ).toBe(2);
});

test("週五到週一整天請假排除週末，共 16 小時", () => {
  // 2026-08-21 是週五，2026-08-24 是週一。
  expect(
    estimateLeaveHours({
      startDate: "2026-08-21", startTime: "09:00", endDate: "2026-08-24", endTime: "18:00",
      settings: DEFAULT_SETTINGS,
    }),
  ).toBe(16);
});

test("純週末區間時數為 0", () => {
  // 2026-08-22（六）～2026-08-23（日）。
  expect(
    estimateLeaveHours({
      startDate: "2026-08-22", startTime: "09:00", endDate: "2026-08-23", endTime: "18:00",
      settings: DEFAULT_SETTINGS,
    }),
  ).toBe(0);
});

test("緩衝只套用在整段請假區間的頭尾兩端，不套用在中間日", () => {
  // 週五 08:55（提早 5 分鐘，在緩衝內）到週一 18:05（延後 5 分鐘，在緩衝內）：
  // 頭尾兩天各多算 5 分鐘，中間週六日不算，總共比 16 小時多 10 分鐘。
  const hours = estimateLeaveHours({
    startDate: "2026-08-21", startTime: "08:55", endDate: "2026-08-24", endTime: "18:05",
    settings: DEFAULT_SETTINGS,
  });
  expect(hours).toBeCloseTo(16 + 10 / 60, 2);
});

test("國定假日排除在外", () => {
  // 週一(08-24)、週二(08-25) 整天請假，週二被列為國定假日時只剩週一 8 小時。
  const hours = estimateLeaveHours({
    startDate: "2026-08-24", startTime: "09:00", endDate: "2026-08-25", endTime: "18:00",
    settings: DEFAULT_SETTINGS,
    holidayDates: new Set(["2026-08-25"]),
  });
  expect(hours).toBe(8);
});

test("非預設設定（08:30–17:30、午休 12:30–13:30、緩衝 15 分）同一套規則整體平移", () => {
  expect(
    estimateLeaveHours({
      startDate: "2026-08-24", startTime: "08:30", endDate: "2026-08-24", endTime: "17:30",
      settings: OTHER_SETTINGS,
    }),
  ).toBe(8);

  // 08:20 比 08:30 早 10 分鐘（頭）、17:40 比 17:30 晚 10 分鐘（尾），
  // 兩者都在 15 分鐘緩衝內，共多算 20 分鐘。
  const hours = estimateLeaveHours({
    startDate: "2026-08-21", startTime: "08:20", endDate: "2026-08-24", endTime: "17:40",
    settings: OTHER_SETTINGS,
  });
  expect(hours).toBeCloseTo(16 + 20 / 60, 2);
});
