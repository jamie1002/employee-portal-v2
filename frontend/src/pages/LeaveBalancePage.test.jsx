import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import LeaveBalancePage from "./LeaveBalancePage";

const mockGetQuota = vi.fn();
vi.mock("../api/leaveQuota.api", () => ({
  getMyLeaveQuota: (...args) => mockGetQuota(...args),
}));

test("顯示四張假別卡片", async () => {
  mockGetQuota.mockResolvedValue({
    quota: [
      { leave_type: "特別休假", quota_hours: 56, used_hours: 0, remaining_hours: 56, period_start: "2026-01-01", period_end: "2027-01-01" },
      { leave_type: "事假", quota_hours: 112, used_hours: 8, remaining_hours: 104, period_start: "2026-01-01", period_end: "2027-01-01" },
      { leave_type: "病假", quota_hours: 240, used_hours: 0, remaining_hours: 240, period_start: "2026-01-01", period_end: "2027-01-01" },
      { leave_type: "公假", quota_hours: null, used_hours: 0, remaining_hours: null, period_start: "2026-01-01", period_end: "2027-01-01" },
    ],
  });

  render(<LeaveBalancePage />);

  await waitFor(() => expect(screen.getByText("特別休假")).toBeInTheDocument());
  expect(screen.getByText("事假")).toBeInTheDocument();
  expect(screen.getByText("病假")).toBeInTheDocument();
  expect(screen.getByText("公假")).toBeInTheDocument();
  expect(screen.getByText(/不設固定上限/)).toBeInTheDocument();
});

test("載入失敗時降級為空清單而不是卡住載入中畫面", async () => {
  mockGetQuota.mockRejectedValue(new Error("network"));

  render(<LeaveBalancePage />);

  await waitFor(() => expect(screen.queryByText("載入中…")).not.toBeInTheDocument());
});
