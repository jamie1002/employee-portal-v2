import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import MonthlyAttendanceSummary from "./MonthlyAttendanceSummary";

const mockGetMyRecords = vi.fn();
vi.mock("../api/attendance.api", () => ({
  getMyRecords: (...args) => mockGetMyRecords(...args),
}));

const mockGetMyPunchRequests = vi.fn();
const mockGetMyLeaveRequests = vi.fn();
const mockGetMyOvertimeRequests = vi.fn();
vi.mock("../api/requests.api", () => ({
  getMyPunchRequests: (...args) => mockGetMyPunchRequests(...args),
  getMyLeaveRequests: (...args) => mockGetMyLeaveRequests(...args),
  getMyOvertimeRequests: (...args) => mockGetMyOvertimeRequests(...args),
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

function renderWithRouter(props) {
  return render(
    <MemoryRouter>
      <MonthlyAttendanceSummary {...props} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockGetMyRecords.mockReset();
  mockGetMyPunchRequests.mockReset();
  mockGetMyLeaveRequests.mockReset();
  mockGetMyOvertimeRequests.mockReset();
  mockGetMyRecords.mockResolvedValue({ records: [] });
  mockGetMyPunchRequests.mockResolvedValue({ requests: [] });
  mockGetMyLeaveRequests.mockResolvedValue({ requests: [] });
  mockGetMyOvertimeRequests.mockResolvedValue({ requests: [] });
});

test("依後端回傳的營業日推算當月區間，不看瀏覽器的今天", async () => {
  renderWithRouter({ punchDate: "2026-08-24" });

  await waitFor(() =>
    expect(mockGetMyRecords).toHaveBeenCalledWith(
      expect.objectContaining({ start_date: "2026-08-01", end_date: "2026-08-31" }),
    ),
  );
});

test("只列異常日，正常的日子不出現", async () => {
  mockGetMyRecords.mockResolvedValue({ records: [NORMAL_DAY, EARLY_LEAVE_DAY] });
  renderWithRouter({ punchDate: "2026-08-24" });

  await waitFor(() => expect(screen.getByText("2026-08-20")).toBeInTheDocument());
  expect(screen.queryByText("2026-08-19")).not.toBeInTheDocument();
});

test("沒有異常日時顯示空狀態", async () => {
  mockGetMyRecords.mockResolvedValue({ records: [NORMAL_DAY] });
  renderWithRouter({ punchDate: "2026-08-24" });

  await waitFor(() => expect(screen.getByText("本月沒有異常出勤紀錄。")).toBeInTheDocument());
});

test("打卡狀態變動後重新載入，避免「今天早退」與「本月沒有異常」並列", async () => {
  const { rerender } = render(
    <MemoryRouter>
      <MonthlyAttendanceSummary punchDate="2026-08-24" refreshKey="true-false" />
    </MemoryRouter>,
  );
  await waitFor(() => expect(mockGetMyRecords).toHaveBeenCalledTimes(1));

  rerender(
    <MemoryRouter>
      <MonthlyAttendanceSummary punchDate="2026-08-24" refreshKey="true-true" />
    </MemoryRouter>,
  );

  await waitFor(() => expect(mockGetMyRecords).toHaveBeenCalledTimes(2));
});

test("異常日未有申請時顯示補打卡／請假快捷連結", async () => {
  mockGetMyRecords.mockResolvedValue({ records: [EARLY_LEAVE_DAY] });
  renderWithRouter({ punchDate: "2026-08-24" });

  await waitFor(() => expect(screen.getByRole("link", { name: "補打卡" })).toBeInTheDocument());
  expect(screen.getByRole("link", { name: "補打卡" })).toHaveAttribute(
    "href",
    "/requests/punch/new?date=2026-08-20",
  );
  expect(screen.getByRole("link", { name: "請假" })).toHaveAttribute(
    "href",
    "/requests/leave/new?date=2026-08-20",
  );
});

test("異常日已有待審補打卡申請時改顯示「已申請，待審核」，不顯示快捷連結", async () => {
  mockGetMyRecords.mockResolvedValue({ records: [EARLY_LEAVE_DAY] });
  mockGetMyPunchRequests.mockResolvedValue({
    requests: [{ id: 1, target_date: "2026-08-20", type: "in", status: "pending", created_at: "2026-08-20T01:00:00+00:00" }],
  });
  renderWithRouter({ punchDate: "2026-08-24" });

  await waitFor(() => expect(screen.getByText("已申請，待審核")).toBeInTheDocument());
  expect(screen.queryByRole("link", { name: "補打卡" })).not.toBeInTheDocument();
});

test("顯示申請中的補打卡／請假／加班清單", async () => {
  mockGetMyPunchRequests.mockResolvedValue({
    requests: [{ id: 1, target_date: "2026-08-20", type: "in", status: "pending", created_at: "2026-08-20T01:00:00+00:00" }],
  });
  mockGetMyLeaveRequests.mockResolvedValue({
    requests: [
      {
        id: 2, leave_type: "事假", status: "pending",
        start_time: "2026-08-21T01:00:00+00:00", end_time: "2026-08-21T10:00:00+00:00",
        created_at: "2026-08-20T02:00:00+00:00",
      },
    ],
  });
  renderWithRouter({ punchDate: "2026-08-24" });

  await waitFor(() => expect(screen.getByText("申請中（2）")).toBeInTheDocument());
  expect(screen.getByText(/補上班卡申請/)).toBeInTheDocument();
  expect(screen.getByText(/請假申請（事假）/)).toBeInTheDocument();
});
