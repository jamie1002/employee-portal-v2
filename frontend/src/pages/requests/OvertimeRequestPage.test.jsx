import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import OvertimeRequestPage from "./OvertimeRequestPage";

vi.mock("../../api/requests.api", () => ({
  createOvertimeRequest: vi.fn(),
}));

const mockGetDemoClock = vi.hoisted(() => vi.fn());
vi.mock("../../api/demo.api", () => ({
  getDemoClock: (...args) => mockGetDemoClock(...args),
}));

beforeEach(() => {
  mockGetDemoClock.mockReset().mockResolvedValue({ virtual_now: "2026-08-24T01:00:00+00:00" }); // 台北 08/24 09:00
});

function renderWithState(state) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/requests/overtime/new", state }]}>
      <Routes>
        <Route path="/requests/overtime/new" element={<OvertimeRequestPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

test("沒有帶入 state 時日期欄位預設帶入展示用虛擬時鐘的今天，不留空", async () => {
  renderWithState(undefined);

  await waitFor(() => expect(screen.getByLabelText("開始日期")).toHaveValue("2026-08-24"));
  expect(screen.getByLabelText("結束日期")).toHaveValue("2026-08-24");
  expect(screen.getByLabelText("加班事由")).toHaveValue("");
});

test("PunchOutConfirmDialog 帶入的預填值會拆解成日期與時間", () => {
  renderWithState({
    prefillStartTime: "2026-08-24T10:30:00+00:00", // 台北 18:30
    prefillEndTime: "2026-08-24T11:30:00+00:00", // 台北 19:30
    prefillReason: "延遲下班加班申請",
  });

  expect(screen.getByLabelText("開始日期")).toHaveValue("2026-08-24");
  expect(screen.getByLabelText("開始時間")).toHaveValue("18:30");
  expect(screen.getByLabelText("結束時間")).toHaveValue("19:30");
  expect(screen.getByLabelText("加班事由")).toHaveValue("延遲下班加班申請");
});
