import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import EmployeePage from "./EmployeePage";

const mockGetUsers = vi.fn();
const mockCreateUser = vi.fn();
const mockUpdateUser = vi.fn();
const mockDeleteUser = vi.fn();
const mockGetAllPermissions = vi.fn();
const mockSetUserPermissions = vi.fn();
vi.mock("../../api/users.api", () => ({
  getUsers: (...args) => mockGetUsers(...args),
  createUser: (...args) => mockCreateUser(...args),
  updateUser: (...args) => mockUpdateUser(...args),
  deleteUser: (...args) => mockDeleteUser(...args),
  getAllPermissions: (...args) => mockGetAllPermissions(...args),
  setUserPermissions: (...args) => mockSetUserPermissions(...args),
}));

const mockGetDepartments = vi.fn();
vi.mock("../../api/departments.api", () => ({
  getDepartments: (...args) => mockGetDepartments(...args),
}));

let mockUser = { id: 1, name: "系統管理者", role: "admin" };
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

const ADMIN_ROW = {
  id: 1, name: "系統管理者", email: "admin@demo.com", role: "admin",
  department_id: null, department_name: null, employee_no: "EMP2019001",
  extension_number: "100", hire_date: "2019-03-01",
};
const EMPLOYEE_ROW = {
  id: 3, name: "陳小華", email: "employee@demo.com", role: "employee",
  department_id: 1, department_name: "研發部", employee_no: "EMP2025001",
  extension_number: "202", hire_date: "2025-09-01",
};

beforeEach(() => {
  mockUser = { id: 1, name: "系統管理者", role: "admin" };
  mockGetUsers.mockReset().mockResolvedValue({ users: [ADMIN_ROW, EMPLOYEE_ROW] });
  mockGetDepartments.mockReset().mockResolvedValue({ departments: [{ id: 1, name: "研發部" }] });
  mockGetAllPermissions.mockReset().mockResolvedValue({
    permissions: [
      { user_id: 3, permission: "holidays.manage", granted_by: 1, granted_by_name: "系統管理者", granted_at: "2026-08-20T02:00:00+00:00" },
    ],
  });
  mockCreateUser.mockReset();
  mockUpdateUser.mockReset();
  mockDeleteUser.mockReset();
  mockSetUserPermissions.mockReset();
});

test("admin 看得到額外權限欄與操作欄，一般員工看不到", async () => {
  render(<EmployeePage />);

  await waitFor(() => expect(screen.getByText("陳小華")).toBeInTheDocument());
  expect(screen.getByText("額外權限")).toBeInTheDocument();
  expect(screen.getByText("國定假日")).toBeInTheDocument();
  expect(screen.getByText(/由 系統管理者 於/)).toBeInTheDocument();
});

test("admin 帳號列不顯示編輯／刪除入口", async () => {
  render(<EmployeePage />);

  await waitFor(() => expect(screen.getByText("陳小華")).toBeInTheDocument());
  expect(screen.getByText("系統管理者帳號不提供編輯入口")).toBeInTheDocument();
});

test("一般員工看不到額外權限欄，且 GET /departments 403 時仍能顯示員工清單", async () => {
  mockUser = { id: 3, name: "陳小華", role: "employee" };
  mockGetDepartments.mockRejectedValue({ response: { status: 403 } });

  render(<EmployeePage />);

  await waitFor(() => expect(screen.getByText("陳小華")).toBeInTheDocument());
  expect(screen.queryByText("額外權限")).not.toBeInTheDocument();
  expect(screen.queryByText("建立員工")).not.toBeInTheDocument();
});

test("建立員工成功後新列出現在清單中", async () => {
  mockCreateUser.mockResolvedValue({
    user: { id: 9, name: "新員工", email: "new@demo.com", role: "employee", department_id: 1, department_name: "研發部", employee_no: "EMP2026099", extension_number: null, hire_date: "2026-08-24" },
  });
  render(<EmployeePage />);
  await waitFor(() => expect(screen.getByText("陳小華")).toBeInTheDocument());

  fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "新員工" } });
  fireEvent.change(screen.getByLabelText("電子郵件"), { target: { value: "new@demo.com" } });
  fireEvent.change(screen.getByLabelText("密碼"), { target: { value: "Demo1234" } });
  fireEvent.click(screen.getByRole("button", { name: "建立員工" }));

  await waitFor(() => expect(screen.getByText("新員工")).toBeInTheDocument());
  expect(mockCreateUser).toHaveBeenCalledWith(
    expect.objectContaining({ name: "新員工", email: "new@demo.com", role: "employee" }),
  );
});

test("編輯員工並變更權限後儲存，只在權限真的變動時才呼叫權限 API", async () => {
  mockUpdateUser.mockResolvedValue({ user: { ...EMPLOYEE_ROW, name: "陳小華改名" } });
  mockSetUserPermissions.mockResolvedValue({
    permissions: [
      { user_id: 3, permission: "settings.manage", granted_by: 1, granted_by_name: "系統管理者", granted_at: "2026-08-24T00:00:00+00:00" },
    ],
  });
  render(<EmployeePage />);
  await waitFor(() => expect(screen.getByText("陳小華")).toBeInTheDocument());

  const rows = screen.getAllByRole("button", { name: "編輯" });
  fireEvent.click(rows[0]);

  fireEvent.click(screen.getByRole("button", { name: "權限" }));
  fireEvent.click(screen.getByLabelText("國定假日管理")); // 取消原本已有的
  fireEvent.click(screen.getByLabelText("考勤設定")); // 新增
  fireEvent.click(screen.getByRole("button", { name: "完成" }));

  fireEvent.click(screen.getByRole("button", { name: "儲存" }));

  await waitFor(() => expect(mockUpdateUser).toHaveBeenCalled());
  await waitFor(() => expect(mockSetUserPermissions).toHaveBeenCalledWith(3, ["settings.manage"]));
});

test("刪除員工需二次確認才會呼叫 API", async () => {
  mockDeleteUser.mockResolvedValue({});
  render(<EmployeePage />);
  await waitFor(() => expect(screen.getByText("陳小華")).toBeInTheDocument());

  fireEvent.click(screen.getAllByRole("button", { name: "刪除" })[0]);
  expect(mockDeleteUser).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "確定刪除？" }));

  await waitFor(() => expect(mockDeleteUser).toHaveBeenCalledWith(3));
  await waitFor(() => expect(screen.queryByText("陳小華")).not.toBeInTheDocument());
});
