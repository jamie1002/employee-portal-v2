import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

test("沒有紀錄時顯示空狀態", () => {
  render(<AttendanceTable records={[]} />);

  expect(screen.getByText("尚無出勤紀錄。")).toBeInTheDocument();
});

test("顯示日期、時間與工時", () => {
  render(<AttendanceTable records={[BASE_RECORD]} />);

  expect(screen.getByText("2026-08-24")).toBeInTheDocument();
  expect(screen.getByText("09:00")).toBeInTheDocument();
  expect(screen.getByText("8.00")).toBeInTheDocument();
});

test("has_changes 與 is_adjusted 是兩種不同的標記，不可混為一談", () => {
  const { rerender } = render(<AttendanceTable records={[{ ...BASE_RECORD, has_changes: true }]} />);

  expect(screen.getByText("有異動申請")).toBeInTheDocument();
  expect(screen.queryByText("已異動")).not.toBeInTheDocument();

  rerender(<AttendanceTable records={[{ ...BASE_RECORD, is_adjusted: true }]} />);

  expect(screen.getByText("已異動")).toBeInTheDocument();
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

  await waitFor(() => expect(screen.getByText("補打卡申請")).toBeInTheDocument());
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

  expect(screen.getByText("陳小華")).toBeInTheDocument();
  expect(screen.getByText("研發部")).toBeInTheDocument();
});
