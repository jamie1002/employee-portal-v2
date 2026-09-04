import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import MyRequestsPage from "./MyRequestsPage";

const mockGetPunch = vi.fn();
const mockGetLeave = vi.fn();
const mockGetOvertime = vi.fn();
vi.mock("../../api/requests.api", () => ({
  getMyPunchRequests: (...args) => mockGetPunch(...args),
  getMyLeaveRequests: (...args) => mockGetLeave(...args),
  getMyOvertimeRequests: (...args) => mockGetOvertime(...args),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <MyRequestsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockGetPunch.mockReset().mockResolvedValue({ requests: [] });
  mockGetLeave.mockReset().mockResolvedValue({ requests: [] });
  mockGetOvertime.mockReset().mockResolvedValue({ requests: [] });
});

test("預設載入補打卡分頁", async () => {
  renderPage();

  await waitFor(() => expect(mockGetPunch).toHaveBeenCalledTimes(1));
  expect(mockGetLeave).not.toHaveBeenCalled();
});

test("切換分頁改呼叫對應的申請類型", async () => {
  renderPage();
  await waitFor(() => expect(mockGetPunch).toHaveBeenCalledTimes(1));

  fireEvent.click(screen.getByRole("button", { name: "請假" }));

  await waitFor(() => expect(mockGetLeave).toHaveBeenCalledTimes(1));
  expect(screen.getByRole("link", { name: "提出請假申請" })).toHaveAttribute("href", "/requests/leave/new");
});

test("切換狀態篩選會帶進查詢參數", async () => {
  renderPage();
  await waitFor(() => expect(mockGetPunch).toHaveBeenCalledTimes(1));

  fireEvent.change(screen.getByRole("combobox"), { target: { value: "approved" } });

  await waitFor(() => expect(mockGetPunch).toHaveBeenLastCalledWith({ status: "approved" }));
});
