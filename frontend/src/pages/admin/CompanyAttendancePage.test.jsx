import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import CompanyAttendancePage from "./CompanyAttendancePage";

const mockGetCompanyRecords = vi.fn();
vi.mock("../../api/attendance.api", () => ({
  getCompanyRecords: (...args) => mockGetCompanyRecords(...args),
}));

const mockGetDepartments = vi.fn();
vi.mock("../../api/departments.api", () => ({
  getDepartments: (...args) => mockGetDepartments(...args),
}));

const mockGetUsers = vi.fn();
vi.mock("../../api/users.api", () => ({
  getUsers: (...args) => mockGetUsers(...args),
}));

let mockUser = { id: 1, name: "系統管理者", role: "admin", permissions: [] };
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

const mockGetDemoClock = vi.fn();
vi.mock("../../api/demo.api", () => ({
  getDemoClock: (...args) => mockGetDemoClock(...args),
}));

const DEPARTMENTS = [
  { id: 1, name: "研發部" },
  { id: 2, name: "業務部" },
];
const USERS = [
  { id: 2, name: "王小明", department_id: 1 },
  { id: 3, name: "陳小華", department_id: 1 },
  { id: 5, name: "張大同", department_id: 2 },
];

beforeEach(() => {
  mockUser = { id: 1, name: "系統管理者", role: "admin", permissions: [] };
  mockGetDepartments.mockReset().mockResolvedValue({ departments: DEPARTMENTS });
  mockGetUsers.mockReset().mockResolvedValue({ users: USERS });
  mockGetCompanyRecords.mockReset().mockResolvedValue({ records: [] });
  mockGetDemoClock.mockReset().mockResolvedValue({ virtual_now: "2026-08-24T01:00:00+00:00" }); // 台北 08/24 09:00
});

test("非 admin 完全不渲染頁面內容（RoleGate）", () => {
  mockUser = { id: 3, name: "陳小華", role: "employee", permissions: [] };
  render(<CompanyAttendancePage />);

  expect(screen.queryByText("全公司出勤")).not.toBeInTheDocument();
});

test("載入後帶出全公司出勤紀錄", async () => {
  mockGetCompanyRecords.mockResolvedValue({
    records: [
      {
        user_id: 2, user_name: "王小明", department_name: "研發部", punch_date: "2026-08-24",
        effective_punch_in_time: null, effective_punch_out_time: null, effective_status: "normal",
        effective_work_hours: "8.00", effective_is_early_leave: false, is_missing_punch_out: false,
        is_adjusted: false, has_changes: false, note: null,
      },
    ],
  });
  render(<CompanyAttendancePage />);

  await waitFor(() => expect(mockGetCompanyRecords).toHaveBeenCalled());
  expect(screen.getAllByText("王小明").length).toBeGreaterThan(0);
});

test("選擇部門後使用者下拉只列該部門成員，切換部門時清空不屬於新部門的已選使用者", async () => {
  render(<CompanyAttendancePage />);
  await waitFor(() => expect(mockGetUsers).toHaveBeenCalled());

  fireEvent.change(screen.getByLabelText("使用者"), { target: { value: "3" } }); // 陳小華（研發部）
  fireEvent.change(screen.getByLabelText("部門"), { target: { value: "1" } }); // 研發部：陳小華仍屬於，保留

  expect(screen.getByLabelText("使用者")).toHaveValue("3");

  fireEvent.change(screen.getByLabelText("部門"), { target: { value: "2" } }); // 業務部：陳小華不屬於，清空
  expect(screen.getByLabelText("使用者")).toHaveValue("");

  const options = within(screen.getByLabelText("使用者")).getAllByRole("option");
  expect(options.map((o) => o.textContent)).toEqual(["全部使用者", "張大同"]);
});

test("篩選條件變動會帶對應參數重新查詢", async () => {
  render(<CompanyAttendancePage />);
  await waitFor(() => expect(mockGetCompanyRecords).toHaveBeenCalledWith(
    expect.objectContaining({ department_id: undefined, user_id: undefined, status: undefined }),
  ));

  fireEvent.change(screen.getByLabelText("部門"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("狀態"), { target: { value: "late" } });

  await waitFor(() => expect(mockGetCompanyRecords).toHaveBeenCalledWith(
    expect.objectContaining({ department_id: "1", status: "late" }),
  ));
});

test("日期欄位維持空白（不限日期），但點開日曆一律顯示展示用虛擬時鐘的今天所在月份", async () => {
  render(<CompanyAttendancePage />);
  await waitFor(() => expect(mockGetDemoClock).toHaveBeenCalled());

  expect(screen.getAllByRole("button", { name: "不限日期" })).toHaveLength(2);

  fireEvent.click(screen.getAllByRole("button", { name: "不限日期" })[0]);
  await waitFor(() => expect(screen.getByText("2026 年 8 月")).toBeInTheDocument());
});
