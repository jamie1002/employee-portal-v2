import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import PunchPanel from "./PunchPanel";

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
  render(<PunchPanel {...props} />);
  return props;
}

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
