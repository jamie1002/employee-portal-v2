import { render, screen } from "@testing-library/react";
import TodayStatusCard from "./TodayStatusCard";

test("尚未打卡時提示今日尚未打卡", () => {
  render(<TodayStatusCard today={{ has_punched_in: false, status: null }} />);

  expect(screen.getByText("今日尚未打卡。")).toBeInTheDocument();
});

test("優先顯示生效值而不是原始值", () => {
  render(
    <TodayStatusCard
      today={{
        has_punched_in: true,
        status: "late",
        punch_in_time: "2026-08-24T01:30:00+00:00",
        work_hours: "7.00",
        effective_status: "normal",
        effective_punch_in_time: "2026-08-24T01:00:00+00:00",
        effective_work_hours: "8.00",
      }}
    />,
  );

  expect(screen.getByText("正常")).toBeInTheDocument();
  expect(screen.getByText("09:00")).toBeInTheDocument();
  expect(screen.getByText("8.00")).toBeInTheDocument();
});

test("工時以兩位小數呈現，沒有值時顯示破折號", () => {
  render(<TodayStatusCard today={{ has_punched_in: true, effective_work_hours: null }} />);

  expect(screen.getAllByText("—").length).toBeGreaterThan(0);
});
