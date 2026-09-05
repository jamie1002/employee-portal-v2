import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import AttendancePage from "./AttendancePage";

const mockGetMyRecords = vi.fn();
vi.mock("../api/attendance.api", () => ({
  getMyRecords: (...args) => mockGetMyRecords(...args),
}));
vi.mock("../api/attendanceChanges.api", () => ({
  getAttendanceChanges: vi.fn().mockResolvedValue({ changes: [] }),
}));

const mockGetDemoClock = vi.fn();
vi.mock("../api/demo.api", () => ({
  getDemoClock: (...args) => mockGetDemoClock(...args),
}));

beforeEach(() => {
  mockGetMyRecords.mockReset();
  mockGetMyRecords.mockResolvedValue({ records: [], total: 0, page: 1, page_size: 10 });
  mockGetDemoClock.mockReset().mockResolvedValue({ virtual_now: "2026-08-24T01:00:00+00:00" }); // 台北 08/24 09:00
});

test("初次載入即帶入分頁參數", async () => {
  render(<AttendancePage />);

  await waitFor(() =>
    expect(mockGetMyRecords).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 10 })),
  );
});

test("切換狀態篩選會帶進查詢參數並回到第一頁", async () => {
  render(<AttendancePage />);
  await waitFor(() => expect(mockGetMyRecords).toHaveBeenCalled());

  fireEvent.change(screen.getByLabelText("狀態"), { target: { value: "early_leave" } });

  await waitFor(() =>
    expect(mockGetMyRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "early_leave", page: 1 }),
    ),
  );
});

test("狀態下拉包含兩個衍生狀態", () => {
  render(<AttendancePage />);

  expect(screen.getByRole("option", { name: "早退" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "未打下班卡" })).toBeInTheDocument();
});

test("分頁按鈕依總筆數啟用或停用", async () => {
  mockGetMyRecords.mockResolvedValue({
    records: [
      {
        user_id: 3,
        punch_date: "2026-08-24",
        effective_status: "normal",
        effective_work_hours: "8.00",
        effective_is_early_leave: false,
        is_missing_punch_out: false,
      },
    ],
    total: 25,
    page: 1,
    page_size: 10,
  });
  render(<AttendancePage />);

  await waitFor(() => expect(screen.getByText("共 25 筆")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "上一頁" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "下一頁" })).toBeEnabled();
});

test("日期欄位維持空白（不限日期），但點開日曆一律顯示展示用虛擬時鐘的今天所在月份", async () => {
  render(<AttendancePage />);
  await waitFor(() => expect(mockGetDemoClock).toHaveBeenCalled());

  expect(screen.getAllByRole("button", { name: "不限日期" })).toHaveLength(2);

  fireEvent.click(screen.getAllByRole("button", { name: "不限日期" })[0]);
  await waitFor(() => expect(screen.getByText("2026 年 8 月")).toBeInTheDocument());
});
