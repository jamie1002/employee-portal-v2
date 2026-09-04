import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import LeaveRequestPage from "./LeaveRequestPage";

const mockCreate = vi.fn();
vi.mock("../../api/requests.api", () => ({
  createLeaveRequest: (...args) => mockCreate(...args),
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
