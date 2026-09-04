import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import ReviewCenterPage from "./ReviewCenterPage";

// RequestTable 同時渲染桌機表格與手機卡片兩套結構（見 docs/UI-SPEC.md §2.4），
// 互動一律 scope 進 <table>（role="table" 唯一），避免撞上卡片版的重複元素。

const mockGetPending = vi.fn();
const mockReview = vi.fn();
vi.mock("../../api/requests.api", () => ({
  getPendingPunchRequests: (...args) => mockGetPending("punch", ...args),
  getPendingLeaveRequests: (...args) => mockGetPending("leave", ...args),
  getPendingOvertimeRequests: (...args) => mockGetPending("overtime", ...args),
  reviewPunchRequest: (...args) => mockReview(...args),
  reviewLeaveRequest: (...args) => mockReview(...args),
  reviewOvertimeRequest: (...args) => mockReview(...args),
}));

const PUNCH_REQUEST = {
  id: 1, applicant_name: "陳小華", department_name: "研發部",
  target_date: "2026-08-24", type: "in", reason: "忘記打卡",
};

beforeEach(() => {
  mockGetPending.mockReset();
  mockReview.mockReset();
  mockGetPending.mockImplementation((kind) =>
    Promise.resolve({ requests: kind === "punch" ? [PUNCH_REQUEST] : [] }),
  );
});

test("分頁標籤顯示各類型的待審筆數", async () => {
  render(<ReviewCenterPage />);

  await waitFor(() => expect(screen.getByText("補打卡（1）")).toBeInTheDocument());
  expect(screen.getByText("請假（0）")).toBeInTheDocument();
});

test("核准後該筆從清單移除", async () => {
  mockReview.mockResolvedValue({ request: { ...PUNCH_REQUEST, status: "approved" } });
  render(<ReviewCenterPage />);
  await waitFor(() => expect(screen.getAllByText("陳小華").length).toBeGreaterThan(0));

  fireEvent.click(within(screen.getByRole("table")).getByRole("button", { name: "核准" }));

  await waitFor(() => expect(screen.queryByText("陳小華")).not.toBeInTheDocument());
  expect(mockReview).toHaveBeenCalledWith(1, { action: "approve" });
});

test("遇到 409 時顯示提示並重新載入清單", async () => {
  mockReview.mockRejectedValue({ response: { status: 409 } });
  render(<ReviewCenterPage />);
  await waitFor(() => expect(screen.getAllByText("陳小華").length).toBeGreaterThan(0));

  fireEvent.click(within(screen.getByRole("table")).getByRole("button", { name: "核准" }));

  await waitFor(() =>
    expect(screen.getByText("此申請已被其他人審核，清單已重新載入。")).toBeInTheDocument(),
  );
  expect(mockGetPending).toHaveBeenCalledWith("punch");
});

test("目前沒有待審申請時顯示空狀態", async () => {
  mockGetPending.mockResolvedValue({ requests: [] });
  render(<ReviewCenterPage />);

  await waitFor(() => expect(screen.getByText("目前沒有待審申請。")).toBeInTheDocument());
});
