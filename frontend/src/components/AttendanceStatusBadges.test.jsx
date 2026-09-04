import { render, screen } from "@testing-library/react";
import AttendanceStatusBadges from "./AttendanceStatusBadges";

test("一般狀態直接顯示對應徽章", () => {
  render(<AttendanceStatusBadges status="late" />);

  expect(screen.getByText("遲到")).toBeInTheDocument();
});

test("正常且同時早退時不顯示「正常」徽章", () => {
  render(<AttendanceStatusBadges status="normal" isEarlyLeave />);

  expect(screen.queryByText("正常")).not.toBeInTheDocument();
  expect(screen.getByText("早退")).toBeInTheDocument();
});

test("正常且未打下班卡時同樣不顯示「正常」徽章", () => {
  render(<AttendanceStatusBadges status="normal" isMissingPunchOut />);

  expect(screen.queryByText("正常")).not.toBeInTheDocument();
  expect(screen.getByText("未打下班卡")).toBeInTheDocument();
});

test("遲到可以與早退並列顯示（兩件事本來就可能同時成立）", () => {
  render(<AttendanceStatusBadges status="late" isEarlyLeave />);

  expect(screen.getByText("遲到")).toBeInTheDocument();
  expect(screen.getByText("早退")).toBeInTheDocument();
});
