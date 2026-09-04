import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import AppShell, { NAV_ITEMS } from "./AppShell";

const mockUseAuth = vi.fn();
vi.mock("../context/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderShell(user) {
  mockUseAuth.mockReturnValue({ user, logout: vi.fn() });
  render(
    <MemoryRouter>
      <AppShell />
    </MemoryRouter>,
  );
}

test("顯示使用者姓名與角色標籤", () => {
  renderShell({ name: "陳小華", role: "employee", permissions: [] });

  expect(screen.getByText("陳小華")).toBeInTheDocument();
  expect(screen.getByText("一般員工")).toBeInTheDocument();
});

test("選單以 hasAccess 過濾，一般員工看得到共通項目", () => {
  renderShell({ name: "陳小華", role: "employee", permissions: [] });

  expect(screen.getByRole("link", { name: "首頁" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "出勤紀錄" })).toBeInTheDocument();
});

test("選單項目一律帶 roles 或 permissions，不得有無條件顯示的漏網項目", () => {
  for (const item of NAV_ITEMS) {
    expect(Boolean(item.roles?.length || item.permissions?.length)).toBe(true);
  }
});

test("手機版：漢堡按鈕點擊後開啟抽屜，點遮罩後關閉", () => {
  renderShell({ name: "陳小華", role: "employee", permissions: [] });

  const sidebar = screen.getByTestId("app-sidebar");
  expect(sidebar).toHaveAttribute("data-state", "closed");
  expect(screen.queryByTestId("drawer-backdrop")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "開啟選單" }));

  expect(sidebar).toHaveAttribute("data-state", "open");
  const backdrop = screen.getByTestId("drawer-backdrop");
  expect(backdrop).toBeInTheDocument();

  fireEvent.click(backdrop);

  expect(sidebar).toHaveAttribute("data-state", "closed");
  expect(screen.queryByTestId("drawer-backdrop")).not.toBeInTheDocument();
});

test("手機版：點選單項目後抽屜關閉", () => {
  renderShell({ name: "陳小華", role: "employee", permissions: [] });

  fireEvent.click(screen.getByRole("button", { name: "開啟選單" }));
  expect(screen.getByTestId("app-sidebar")).toHaveAttribute("data-state", "open");

  fireEvent.click(screen.getByRole("link", { name: "首頁" }));

  expect(screen.getByTestId("app-sidebar")).toHaveAttribute("data-state", "closed");
});
