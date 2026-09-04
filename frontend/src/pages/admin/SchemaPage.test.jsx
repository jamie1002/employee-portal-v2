import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import SchemaPage from "./SchemaPage";

const mockGetSchemaOverview = vi.fn();
const mockGetTablePreview = vi.fn();
vi.mock("../../api/schema.api", () => ({
  getSchemaOverview: (...args) => mockGetSchemaOverview(...args),
  getTablePreview: (...args) => mockGetTablePreview(...args),
}));

let mockUser = { id: 1, name: "系統管理者", role: "admin" };
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

const TABLES = {
  departments: [{ name: "id", type: "integer", nullable: false, default: null, is_primary_key: true, is_foreign_key: false, references: null }],
  users: [
    { name: "id", type: "integer", nullable: false, default: null, is_primary_key: true, is_foreign_key: false, references: null },
    { name: "department_id", type: "integer", nullable: true, default: null, is_primary_key: false, is_foreign_key: true, references: { table: "departments", column: "id" } },
  ],
};

beforeEach(() => {
  mockUser = { id: 1, name: "系統管理者", role: "admin" };
  mockGetSchemaOverview.mockReset().mockResolvedValue({ tables: TABLES });
  mockGetTablePreview.mockReset().mockResolvedValue({ rows: [{ id: 1, name: "研發部" }] });
});

test("非 admin 完全不渲染頁面內容", () => {
  mockUser = { id: 3, name: "陳小華", role: "employee" };
  render(<SchemaPage />);

  expect(screen.queryByText("資料庫管理")).not.toBeInTheDocument();
});

test("載入後自動選第一個表（字母排序）並顯示資料內容", async () => {
  render(<SchemaPage />);

  await waitFor(() => expect(screen.getByLabelText("資料表")).toHaveValue("departments"));
  await waitFor(() => expect(screen.getAllByText("研發部").length).toBeGreaterThan(0));
  expect(mockGetTablePreview).toHaveBeenCalledWith("departments");
});

test("切換到結構定義顯示欄位的主鍵與外鍵參照", async () => {
  render(<SchemaPage />);
  await waitFor(() => expect(screen.getByLabelText("資料表")).toHaveValue("departments"));

  fireEvent.change(screen.getByLabelText("資料表"), { target: { value: "users" } });
  fireEvent.click(screen.getByRole("button", { name: "結構定義" }));

  expect(screen.getAllByText("departments.id").length).toBeGreaterThan(0);
});

test("切回看過的表不重複打 API", async () => {
  render(<SchemaPage />);
  await waitFor(() => expect(mockGetTablePreview).toHaveBeenCalledWith("departments"));

  fireEvent.change(screen.getByLabelText("資料表"), { target: { value: "users" } });
  await waitFor(() => expect(mockGetTablePreview).toHaveBeenCalledWith("users"));

  fireEvent.change(screen.getByLabelText("資料表"), { target: { value: "departments" } });
  await waitFor(() => expect(screen.getAllByText("研發部").length).toBeGreaterThan(0));

  expect(mockGetTablePreview).toHaveBeenCalledTimes(2);
});
