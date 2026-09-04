import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import HolidayManagementPage from "./HolidayManagementPage";

const mockGetHolidays = vi.fn();
const mockCreateHoliday = vi.fn();
const mockDeleteHoliday = vi.fn();
vi.mock("../../api/holidays.api", () => ({
  getHolidays: (...args) => mockGetHolidays(...args),
  createHoliday: (...args) => mockCreateHoliday(...args),
  deleteHoliday: (...args) => mockDeleteHoliday(...args),
}));

let mockUser = { id: 1, name: "系統管理者", role: "admin", permissions: [] };
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

beforeEach(() => {
  mockUser = { id: 1, name: "系統管理者", role: "admin", permissions: [] };
  mockGetHolidays.mockReset().mockResolvedValue({
    holidays: [{ holiday_date: "2026-01-01", name: "元旦" }],
  });
  mockCreateHoliday.mockReset();
  mockDeleteHoliday.mockReset();
});

test("非 admin 且無 holidays.manage 權限時完全不渲染", () => {
  mockUser = { id: 3, name: "陳小華", role: "employee", permissions: [] };
  render(<HolidayManagementPage />);

  expect(screen.queryByText("國定假日")).not.toBeInTheDocument();
});

test("持有 holidays.manage 權限的一般員工也能看到頁面", async () => {
  mockUser = { id: 3, name: "陳小華", role: "employee", permissions: ["holidays.manage"] };
  render(<HolidayManagementPage />);

  await waitFor(() => expect(screen.getAllByText("元旦").length).toBeGreaterThan(0));
});

test("新增假日後依日期排序插入清單", async () => {
  mockCreateHoliday.mockResolvedValue({ holiday: { holiday_date: "2025-12-25", name: "聖誕節" } });
  render(<HolidayManagementPage />);
  await waitFor(() => expect(screen.getAllByText("元旦").length).toBeGreaterThan(0));

  fireEvent.change(screen.getByLabelText("日期"), { target: { value: "2025-12-25" } });
  fireEvent.change(screen.getByLabelText("名稱"), { target: { value: "聖誕節" } });
  fireEvent.click(screen.getByRole("button", { name: "新增假日" }));

  await waitFor(() => expect(screen.getAllByText("聖誕節").length).toBeGreaterThan(0));
  // 表格版（role="table" 唯一）的列序才是排序驗收依據，卡片版不涉及 DOM 順序斷言。
  const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1); // 排除表頭
  expect(rows[0]).toHaveTextContent("2025-12-25");
});

test("刪除假日直接執行，不需二次確認", async () => {
  mockDeleteHoliday.mockResolvedValue(undefined);
  render(<HolidayManagementPage />);
  await waitFor(() => expect(screen.getAllByText("元旦").length).toBeGreaterThan(0));

  fireEvent.click(screen.getAllByRole("button", { name: "刪除" })[0]);

  await waitFor(() => expect(mockDeleteHoliday).toHaveBeenCalledWith("2026-01-01"));
  await waitFor(() => expect(screen.queryByText("元旦")).not.toBeInTheDocument());
});
