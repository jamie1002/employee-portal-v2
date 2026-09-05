import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import PunchRequestPage from "./PunchRequestPage";

const mockCreate = vi.fn();
vi.mock("../../api/requests.api", () => ({
  createPunchRequest: (...args) => mockCreate(...args),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockGetDemoClock = vi.hoisted(() => vi.fn());
vi.mock("../../api/demo.api", () => ({
  getDemoClock: (...args) => mockGetDemoClock(...args),
}));

function renderPage(initialPath = "/requests/punch/new") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <PunchRequestPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockCreate.mockReset();
  mockNavigate.mockReset();
  mockGetDemoClock.mockReset().mockResolvedValue({ virtual_now: "2026-08-24T01:00:00+00:00" }); // 台北 08/24 09:00
});

test("預設只顯示上班時間欄位", () => {
  renderPage();

  expect(screen.getByLabelText("上班時間")).toBeInTheDocument();
  expect(screen.queryByLabelText("下班時間")).not.toBeInTheDocument();
});

test("選擇補上下班卡時同時顯示兩個時間欄位", () => {
  renderPage();

  fireEvent.change(screen.getByLabelText("類型"), { target: { value: "both" } });

  expect(screen.getByLabelText("上班時間")).toBeInTheDocument();
  expect(screen.getByLabelText("下班時間")).toBeInTheDocument();
});

test("查詢參數 date 會預填日期欄位", () => {
  renderPage("/requests/punch/new?date=2026-08-24");

  expect(screen.getByLabelText("日期")).toHaveValue("2026-08-24");
});

test("沒有查詢參數時日期欄位預設帶入展示用虛擬時鐘的今天，不留空", async () => {
  renderPage();

  await vi.waitFor(() => expect(screen.getByLabelText("日期")).toHaveValue("2026-08-24"));
});

test("送出成功後導向我的申請頁", async () => {
  mockCreate.mockResolvedValue({ request: { id: 1 } });
  renderPage();

  fireEvent.change(screen.getByLabelText("日期"), { target: { value: "2026-08-24" } });
  fireEvent.change(screen.getByLabelText("上班時間"), { target: { value: "09:00" } });
  fireEvent.change(screen.getByLabelText("申請理由"), { target: { value: "忘記打卡" } });
  fireEvent.click(screen.getByRole("button", { name: "送出申請" }));

  await vi.waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/requests"));
  expect(mockCreate).toHaveBeenCalledWith(
    expect.objectContaining({ type: "in", target_date: "2026-08-24", requested_in_time: "2026-08-24T09:00:00+08:00" }),
  );
});

test("送出失敗時顯示後端錯誤訊息", async () => {
  mockCreate.mockRejectedValue({ response: { data: { error: { message: "這天已經有一筆待審或已核准的補打卡申請。" } } } });
  renderPage();

  fireEvent.change(screen.getByLabelText("日期"), { target: { value: "2026-08-24" } });
  fireEvent.change(screen.getByLabelText("上班時間"), { target: { value: "09:00" } });
  fireEvent.change(screen.getByLabelText("申請理由"), { target: { value: "忘記打卡" } });
  fireEvent.click(screen.getByRole("button", { name: "送出申請" }));

  expect(await screen.findByText("這天已經有一筆待審或已核准的補打卡申請。")).toBeInTheDocument();
});
