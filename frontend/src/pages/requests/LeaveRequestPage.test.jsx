import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import LeaveRequestPage from "./LeaveRequestPage";

const mockCreate = vi.fn();
vi.mock("../../api/requests.api", () => ({
  createLeaveRequest: (...args) => mockCreate(...args),
}));

const mockGetSettings = vi.hoisted(() => vi.fn());
vi.mock("../../api/settings.api", () => ({
  getSettings: (...args) => mockGetSettings(...args),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <LeaveRequestPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockCreate.mockReset();
  mockNavigate.mockReset();
  mockGetSettings.mockReset().mockResolvedValue({
    settings: {
      work_start_time: "09:00:00", work_end_time: "18:00:00",
      lunch_start_time: "12:00:00", lunch_end_time: "13:00:00", grace_period_minutes: 10,
    },
  });
});

test("預設假別為事假時申請理由為必填", () => {
  renderPage();

  expect(screen.getByLabelText(/申請理由/)).toBeRequired();
});

test("選擇特別休假時申請理由變為非必填", () => {
  renderPage();

  fireEvent.change(screen.getByLabelText("假別"), { target: { value: "特別休假" } });

  expect(screen.getByLabelText(/申請理由/)).not.toBeRequired();
  expect(screen.getByText(/特別休假可不填/)).toBeInTheDocument();
});

test("送出成功後導向我的申請頁", async () => {
  mockCreate.mockResolvedValue({ request: { id: 1 } });
  renderPage();

  fireEvent.change(screen.getByLabelText("開始日期"), { target: { value: "2026-08-24" } });
  fireEvent.change(screen.getByLabelText("開始時間"), { target: { value: "09:00" } });
  fireEvent.change(screen.getByLabelText("結束日期"), { target: { value: "2026-08-24" } });
  fireEvent.change(screen.getByLabelText("結束時間"), { target: { value: "18:00" } });
  fireEvent.change(screen.getByLabelText(/申請理由/), { target: { value: "個人事務" } });
  fireEvent.click(screen.getByRole("button", { name: "送出申請" }));

  await vi.waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/requests"));
  expect(mockCreate).toHaveBeenCalledWith(
    expect.objectContaining({
      leave_type: "事假",
      start_time: "2026-08-24T09:00:00+08:00",
      end_time: "2026-08-24T18:00:00+08:00",
    }),
  );
});

test("勾選整天會自動帶入表定上下班時間並停用時間欄位", async () => {
  renderPage();

  await waitFor(() => expect(screen.getByText(/09:00 ~ 18:00/)).toBeInTheDocument());

  fireEvent.click(screen.getByRole("checkbox", { name: /整天/ }));

  expect(screen.getByLabelText("開始時間")).toHaveValue("09:00");
  expect(screen.getByLabelText("開始時間")).toBeDisabled();
  expect(screen.getByLabelText("結束時間")).toHaveValue("18:00");
  expect(screen.getByLabelText("結束時間")).toBeDisabled();

  fireEvent.click(screen.getByRole("checkbox", { name: /整天/ }));
  expect(screen.getByLabelText("開始時間")).not.toBeDisabled();
});
