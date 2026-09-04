import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import PunchPanel from "./PunchPanel";

const mockMarkTodayNote = vi.fn();
vi.mock("../api/attendance.api", () => ({
  markTodayNote: (...args) => mockMarkTodayNote(...args),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderPanel(overrides = {}) {
  const props = {
    today: { has_punched_in: false, has_punched_out: false, is_workday: true },
    isLoading: false,
    isSubmitting: false,
    error: null,
    onPunchIn: vi.fn(),
    onPunchOut: vi.fn(),
    ...overrides,
  };
  render(
    <MemoryRouter>
      <PunchPanel {...props} />
    </MemoryRouter>,
  );
  return props;
}

beforeEach(() => {
  mockMarkTodayNote.mockReset();
  mockNavigate.mockReset();
});

test("尚未打卡時只有上班打卡可按", () => {
  renderPanel();

  expect(screen.getByRole("button", { name: "上班打卡" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "下班打卡" })).toBeDisabled();
});

test("已上班未下班時只有下班打卡可按", () => {
  renderPanel({ today: { has_punched_in: true, has_punched_out: false, is_workday: true } });

  expect(screen.getByRole("button", { name: "上班打卡" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "下班打卡" })).toBeEnabled();
});

test("上下班都打完後兩顆按鈕都停用", () => {
  renderPanel({ today: { has_punched_in: true, has_punched_out: true, is_workday: true } });

  expect(screen.getByRole("button", { name: "上班打卡" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "下班打卡" })).toBeDisabled();
});

test("點擊上班打卡會呼叫對應的處理函式", () => {
  const props = renderPanel();

  fireEvent.click(screen.getByRole("button", { name: "上班打卡" }));

  expect(props.onPunchIn).toHaveBeenCalledTimes(1);
});

test("送出中時按鈕停用並顯示處理中", () => {
  renderPanel({ isSubmitting: true });

  expect(screen.getAllByRole("button", { name: "處理中…" })).toHaveLength(2);
});

test("顯示後端回傳的錯誤訊息", () => {
  renderPanel({ error: "今日已完成上班打卡。" });

  expect(screen.getByText("今日已完成上班打卡。")).toBeInTheDocument();
});

test("非上班日顯示加班提醒", () => {
  renderPanel({ today: { has_punched_in: false, has_punched_out: false, is_workday: false } });

  expect(screen.getByText(/今天是非上班日/)).toBeInTheDocument();
});

test("下班打卡超過晚下班門檻時彈出確認彈窗", async () => {
  const attendance = {
    has_punched_in: true, has_punched_out: true, is_workday: true,
    punch_out_time: "2026-08-24T11:30:00+00:00",
    late_punch_out_threshold: "2026-08-24T11:00:00+00:00",
    normal_work_end: "2026-08-24T10:00:00+00:00",
    overtime_eligible_start: "2026-08-24T10:30:00+00:00",
  };
  renderPanel({
    today: { has_punched_in: true, has_punched_out: false, is_workday: true },
    onPunchOut: vi.fn().mockResolvedValue(attendance),
  });

  fireEvent.click(screen.getByRole("button", { name: "下班打卡" }));

  expect(await screen.findByText("下班時間較晚")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "前往申請加班" })).toBeInTheDocument();
});

test("準時下班不彈出確認彈窗", async () => {
  const attendance = {
    has_punched_in: true, has_punched_out: true, is_workday: true,
    punch_out_time: "2026-08-24T10:00:00+00:00",
    late_punch_out_threshold: "2026-08-24T11:00:00+00:00",
  };
  renderPanel({
    today: { has_punched_in: true, has_punched_out: false, is_workday: true },
    onPunchOut: vi.fn().mockResolvedValue(attendance),
  });

  fireEvent.click(screen.getByRole("button", { name: "下班打卡" }));

  await waitFor(() => expect(screen.queryByText("下班時間較晚")).not.toBeInTheDocument());
});

test("選擇前往申請加班會帶著預填值導向加班申請頁", async () => {
  const attendance = {
    has_punched_in: true, has_punched_out: true, is_workday: true,
    punch_out_time: "2026-08-24T11:30:00+00:00",
    late_punch_out_threshold: "2026-08-24T11:00:00+00:00",
    normal_work_end: "2026-08-24T10:00:00+00:00",
    overtime_eligible_start: "2026-08-24T10:30:00+00:00",
  };
  renderPanel({
    today: { has_punched_in: true, has_punched_out: false, is_workday: true },
    onPunchOut: vi.fn().mockResolvedValue(attendance),
  });
  fireEvent.click(screen.getByRole("button", { name: "下班打卡" }));
  await screen.findByText("下班時間較晚");

  fireEvent.click(screen.getByRole("button", { name: "前往申請加班" }));

  expect(mockNavigate).toHaveBeenCalledWith(
    "/requests/overtime/new",
    expect.objectContaining({
      state: expect.objectContaining({
        prefillStartTime: attendance.overtime_eligible_start,
        prefillEndTime: attendance.punch_out_time,
      }),
    }),
  );
});

test("選擇算作處理私人事務會呼叫備註 API 並關閉彈窗", async () => {
  const attendance = {
    has_punched_in: true, has_punched_out: true, is_workday: true,
    punch_out_time: "2026-08-24T11:30:00+00:00",
    late_punch_out_threshold: "2026-08-24T11:00:00+00:00",
  };
  mockMarkTodayNote.mockResolvedValue({});
  renderPanel({
    today: { has_punched_in: true, has_punched_out: false, is_workday: true },
    onPunchOut: vi.fn().mockResolvedValue(attendance),
  });
  fireEvent.click(screen.getByRole("button", { name: "下班打卡" }));
  await screen.findByText("下班時間較晚");

  fireEvent.click(screen.getByRole("button", { name: "算作處理私人事務" }));

  await waitFor(() => expect(mockMarkTodayNote).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.queryByText("下班時間較晚")).not.toBeInTheDocument());
});

test("可加班時間不足 30 分鐘時不顯示前往申請加班選項", async () => {
  const attendance = {
    has_punched_in: true, has_punched_out: true, is_workday: true,
    punch_out_time: "2026-08-24T11:10:00+00:00",
    late_punch_out_threshold: "2026-08-24T11:00:00+00:00",
    overtime_eligible_start: "2026-08-24T10:50:00+00:00",
  };
  renderPanel({
    today: { has_punched_in: true, has_punched_out: false, is_workday: true },
    onPunchOut: vi.fn().mockResolvedValue(attendance),
  });

  fireEvent.click(screen.getByRole("button", { name: "下班打卡" }));

  await screen.findByText("下班時間較晚");
  expect(screen.queryByRole("button", { name: "前往申請加班" })).not.toBeInTheDocument();
});
