import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import DepartmentPage from "./DepartmentPage";

const mockGetDepartments = vi.fn();
const mockCreateDepartment = vi.fn();
const mockUpdateDepartment = vi.fn();
const mockDeleteDepartment = vi.fn();
vi.mock("../../api/departments.api", () => ({
  getDepartments: (...args) => mockGetDepartments(...args),
  createDepartment: (...args) => mockCreateDepartment(...args),
  updateDepartment: (...args) => mockUpdateDepartment(...args),
  deleteDepartment: (...args) => mockDeleteDepartment(...args),
}));

const mockGetUsers = vi.fn();
vi.mock("../../api/users.api", () => ({
  getUsers: (...args) => mockGetUsers(...args),
}));

let mockUser = { id: 1, name: "系統管理者", role: "admin" };
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

const DEPARTMENT = { id: 1, name: "研發部", manager_id: 2, manager_name: "王小明", member_count: 2 };

beforeEach(() => {
  mockUser = { id: 1, name: "系統管理者", role: "admin" };
  mockGetDepartments.mockReset().mockResolvedValue({ departments: [DEPARTMENT] });
  mockGetUsers.mockReset().mockResolvedValue({
    users: [
      { id: 1, name: "系統管理者", role: "admin" },
      { id: 2, name: "王小明", role: "manager" },
      { id: 3, name: "陳小華", role: "employee" },
    ],
  });
  mockCreateDepartment.mockReset();
  mockUpdateDepartment.mockReset();
  mockDeleteDepartment.mockReset();
});

test("非 admin 完全不渲染頁面內容（RoleGate）", () => {
  mockUser = { id: 3, name: "陳小華", role: "employee" };
  render(<DepartmentPage />);

  expect(screen.queryByText("部門管理")).not.toBeInTheDocument();
});

test("顯示部門清單含主管與成員人數", async () => {
  render(<DepartmentPage />);

  await waitFor(() => expect(screen.getByText("研發部")).toBeInTheDocument());
  const row = screen.getByText("研發部").closest("tr");
  expect(row).toHaveTextContent("王小明");
  expect(row).toHaveTextContent("2");
});

test("建立部門成功後新列出現在清單中", async () => {
  mockCreateDepartment.mockResolvedValue({ department: { id: 2, name: "業務部", manager_id: null, manager_name: null, member_count: 0 } });
  render(<DepartmentPage />);
  await waitFor(() => expect(screen.getByText("研發部")).toBeInTheDocument());

  fireEvent.change(screen.getByLabelText("部門名稱"), { target: { value: "業務部" } });
  fireEvent.click(screen.getByRole("button", { name: "建立部門" }));

  await waitFor(() => expect(screen.getByText("業務部")).toBeInTheDocument());
});

test("刪除部門需二次確認才會呼叫 API", async () => {
  mockDeleteDepartment.mockResolvedValue({});
  render(<DepartmentPage />);
  await waitFor(() => expect(screen.getByText("研發部")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "刪除" }));
  expect(mockDeleteDepartment).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "確定刪除？" }));

  await waitFor(() => expect(mockDeleteDepartment).toHaveBeenCalledWith(1));
});
