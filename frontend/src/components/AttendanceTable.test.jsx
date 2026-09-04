import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import AttendanceTable from "./AttendanceTable";

const mockGetChanges = vi.fn();
vi.mock("../api/attendanceChanges.api", () => ({
  getAttendanceChanges: (...args) => mockGetChanges(...args),
}));

const BASE_RECORD = {
  user_id: 3,
  punch_date: "2026-08-24",
  effective_punch_in_time: "2026-08-24T01:00:00+00:00",
  effective_punch_out_time: "2026-08-24T10:00:00+00:00",
  effective_status: "normal",
  effective_work_hours: "8.00",
  effective_is_early_leave: false,
  is_missing_punch_out: false,
  is_adjusted: false,
  has_changes: false,
  note: null,
};

beforeEach(() => {
  mockGetChanges.mockReset();
  mockGetChanges.mockResolvedValue({ changes: [] });
});

// 桌機表格版（role="table" 唯一）與手機卡片版（data-testid="attendance-cards"）
// 同一份資料會渲染兩份 DOM——這是刻意的雙結構（見 docs/UI-SPEC.md §2.4），
// 桌機斷言一律 scope 進 <table>，避免撞上卡片版的重複文字。

test("沒有紀錄時顯示空狀態", () => {
  render(<AttendanceTable records={[]} />);

  expect(screen.getByText("尚無出勤紀錄。")).toBeInTheDocument();
});

test("顯示日期、時間與工時（桌機表格版）", () => {
  render(<AttendanceTable records={[BASE_RECORD]} />);

  const table = within(screen.getByRole("table"));
  expect(table.getByText("2026-08-24")).toBeInTheDocument();
  expect(table.getByText("09:00")).toBeInTheDocument();
  expect(table.getByText("8.00")).toBeInTheDocument();
});

test("顯示日期、時間與工時（手機卡片版）", () => {
  render(<AttendanceTable records={[BASE_RECORD]} />);

  const cards = within(screen.getByTestId("attendance-cards"));
  expect(cards.getByText("2026-08-24")).toBeInTheDocument();
  expect(cards.getByText("09:00")).toBeInTheDocument();
  expect(cards.getByText("8.00")).toBeInTheDocument();
});

test("has_changes 與 is_adjusted 是兩種不同的標記，不可混為一談", () => {
  const { rerender } = render(<AttendanceTable records={[{ ...BASE_RECORD, has_changes: true }]} />);

  expect(screen.getAllByText("有異動申請").length).toBeGreaterThan(0);
  expect(screen.queryByText("已異動")).not.toBeInTheDocument();

  rerender(<AttendanceTable records={[{ ...BASE_RECORD, is_adjusted: true }]} />);

  expect(screen.getAllByText("已異動").length).toBeGreaterThan(0);
  expect(screen.queryByText("有異動申請")).not.toBeInTheDocument();
});

test("勾選顯示異動後才去載入申請明細", async () => {
  mockGetChanges.mockResolvedValue({
    changes: [
      {
        source: "punch_request",
        request_id: 1,
        user_id: 3,
        start_date: "2026-08-24",
        end_date: "2026-08-24",
        status: "pending",
        submitted_at: "2026-08-24T02:00:00+00:00",
        punch_type: "in",
        requested_in_time: "2026-08-24T01:00:00+00:00",
      },
    ],
  });
  render(<AttendanceTable records={[{ ...BASE_RECORD, has_changes: true }]} />);

  expect(mockGetChanges).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("checkbox"));

  await waitFor(() => expect(screen.getAllByText("補打卡申請").length).toBeGreaterThan(0));
  expect(mockGetChanges).toHaveBeenCalledWith(
    expect.objectContaining({ start_date: "2026-08-24", end_date: "2026-08-24" }),
  );
});

test("showUser 模式多顯示姓名與部門欄", () => {
  render(
    <AttendanceTable
      records={[{ ...BASE_RECORD, user_name: "陳小華", department_name: "研發部" }]}
      showUser
    />,
  );

  expect(screen.getAllByText("陳小華").length).toBeGreaterThan(0);
  expect(screen.getAllByText("研發部").length).toBeGreaterThan(0);
});
