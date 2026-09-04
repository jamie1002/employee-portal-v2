import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import MonthlyAttendanceSummary from "./MonthlyAttendanceSummary";

const mockGetMyRecords = vi.fn();
vi.mock("../api/attendance.api", () => ({
  getMyRecords: (...args) => mockGetMyRecords(...args),
}));

const NORMAL_DAY = {
  punch_date: "2026-08-19",
  effective_status: "normal",
  effective_is_early_leave: false,
  is_missing_punch_out: false,
};
const EARLY_LEAVE_DAY = {
  punch_date: "2026-08-20",
  effective_status: "normal",
  effective_is_early_leave: true,
  is_missing_punch_out: false,
};

beforeEach(() => {
  mockGetMyRecords.mockReset();
  mockGetMyRecords.mockResolvedValue({ records: [] });
});

test("依後端回傳的營業日推算當月區間，不看瀏覽器的今天", async () => {
  render(<MonthlyAttendanceSummary punchDate="2026-08-24" />);

  await waitFor(() =>
    expect(mockGetMyRecords).toHaveBeenCalledWith(
      expect.objectContaining({ start_date: "2026-08-01", end_date: "2026-08-31" }),
    ),
  );
});

test("只列異常日，正常的日子不出現", async () => {
  mockGetMyRecords.mockResolvedValue({ records: [NORMAL_DAY, EARLY_LEAVE_DAY] });
  render(<MonthlyAttendanceSummary punchDate="2026-08-24" />);

  await waitFor(() => expect(screen.getByText("2026-08-20")).toBeInTheDocument());
  expect(screen.queryByText("2026-08-19")).not.toBeInTheDocument();
});

test("沒有異常日時顯示空狀態", async () => {
  mockGetMyRecords.mockResolvedValue({ records: [NORMAL_DAY] });
  render(<MonthlyAttendanceSummary punchDate="2026-08-24" />);

  await waitFor(() => expect(screen.getByText("本月沒有異常出勤紀錄。")).toBeInTheDocument());
});

test("打卡狀態變動後重新載入，避免「今天早退」與「本月沒有異常」並列", async () => {
  const { rerender } = render(<MonthlyAttendanceSummary punchDate="2026-08-24" refreshKey="true-false" />);
  await waitFor(() => expect(mockGetMyRecords).toHaveBeenCalledTimes(1));

  rerender(<MonthlyAttendanceSummary punchDate="2026-08-24" refreshKey="true-true" />);

  await waitFor(() => expect(mockGetMyRecords).toHaveBeenCalledTimes(2));
});
