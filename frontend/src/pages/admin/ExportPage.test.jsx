import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import ExportPage from "./ExportPage";

const mockGetExportPreview = vi.fn();
const mockDownloadExportXlsx = vi.fn();
vi.mock("../../api/export.api", () => ({
  getExportPreview: (...args) => mockGetExportPreview(...args),
  downloadExportXlsx: (...args) => mockDownloadExportXlsx(...args),
}));

const mockGetDepartments = vi.fn();
vi.mock("../../api/departments.api", () => ({
  getDepartments: (...args) => mockGetDepartments(...args),
}));

const mockGetUsers = vi.fn();
vi.mock("../../api/users.api", () => ({
  getUsers: (...args) => mockGetUsers(...args),
}));

const mockGetDemoClock = vi.fn();
vi.mock("../../api/demo.api", () => ({
  getDemoClock: (...args) => mockGetDemoClock(...args),
}));

let mockUser = { id: 1, name: "系統管理者", role: "admin", department_id: null, permissions: [] };
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

const USERS = [
  { id: 2, name: "王小明", department_id: 1 },
  { id: 3, name: "陳小華", department_id: 1 },
  { id: 5, name: "張大同", department_id: 2 },
];

beforeEach(() => {
  mockUser = { id: 1, name: "系統管理者", role: "admin", department_id: null, permissions: [] };
  mockGetDepartments.mockReset().mockResolvedValue({ departments: [{ id: 1, name: "研發部" }, { id: 2, name: "業務部" }] });
  mockGetUsers.mockReset().mockResolvedValue({ users: USERS });
  mockGetExportPreview.mockReset();
  mockDownloadExportXlsx.mockReset();
  mockGetDemoClock.mockReset().mockResolvedValue({ virtual_now: "2026-08-24T01:00:00+00:00" }); // 台北 08/24 09:00
});

test("非 admin 且無 exports.run 權限時完全不渲染", () => {
  mockUser = { id: 5, name: "張大同", role: "employee", department_id: 2, permissions: [] };
  render(<ExportPage />);

  expect(screen.queryByText("匯出報表")).not.toBeInTheDocument();
});

test("admin 看得到部門篩選；manager 看不到，改顯示限縮提示（不得出現「主管身分」）", async () => {
  const { rerender } = render(<ExportPage />);
  await waitFor(() => expect(screen.getByRole("combobox", { name: "部門" })).toBeInTheDocument());

  mockUser = { id: 2, name: "王小明", role: "manager", department_id: 1, permissions: [] };
  rerender(<ExportPage />);

  await waitFor(() => expect(screen.queryByRole("combobox", { name: "部門" })).not.toBeInTheDocument());
  const hint = screen.getByText(/僅能匯出所屬部門資料/);
  expect(hint.textContent).not.toContain("主管身分");
});

test("員工資料類型不顯示員工篩選與日期篩選；出勤類型才顯示", async () => {
  render(<ExportPage />);
  await waitFor(() => expect(screen.getByLabelText("資料類型")).toBeInTheDocument());

  expect(screen.queryByLabelText("員工")).not.toBeInTheDocument();
  expect(screen.queryByText("起始日期")).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("資料類型"), { target: { value: "attendance" } });

  expect(screen.getByLabelText("員工")).toBeInTheDocument();
  expect(screen.getByText("起始日期")).toBeInTheDocument();
});

test("受限縮者的員工下拉只列自己部門的人", async () => {
  mockUser = { id: 2, name: "王小明", role: "manager", department_id: 1, permissions: [] };
  render(<ExportPage />);
  await waitFor(() => expect(mockGetUsers).toHaveBeenCalled());

  fireEvent.change(screen.getByLabelText("資料類型"), { target: { value: "attendance" } });

  const options = screen.getByLabelText("員工").querySelectorAll("option");
  const names = Array.from(options).map((o) => o.textContent);
  expect(names).toEqual(["全部", "王小明", "陳小華"]);
});

test("取消勾選所有欄位後預覽與下載按鈕都停用", async () => {
  render(<ExportPage />);
  await waitFor(() => expect(screen.getByText("欄位")).toBeInTheDocument());

  const fieldSection = screen.getByText("欄位").parentElement;
  for (const checkbox of fieldSection.querySelectorAll('input[type="checkbox"]')) {
    fireEvent.click(checkbox);
  }

  expect(screen.getByRole("button", { name: "預覽" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "下載 .xlsx" })).toBeDisabled();
});

test("點預覽會呼叫 getExportPreview 並顯示結果表格", async () => {
  mockGetExportPreview.mockResolvedValue({
    columns: [{ key: "name", label: "姓名" }],
    rows: [["陳小華"]],
    total: 1,
  });
  render(<ExportPage />);
  await waitFor(() => expect(screen.getByLabelText("員工編號")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "預覽" }));

  await waitFor(() => expect(screen.getAllByText("陳小華").length).toBeGreaterThan(0));
  expect(mockGetExportPreview).toHaveBeenCalledWith("employees", {}, expect.arrayContaining(["name"]));
});

test("下載失敗時從 blob 錯誤回應解析出真正的錯誤訊息", async () => {
  const errorBlob = new Blob([JSON.stringify({ error: { message: "尚未指派所屬部門，無法匯出資料。" } })], {
    type: "application/json",
  });
  mockDownloadExportXlsx.mockRejectedValue({ response: { data: errorBlob } });
  render(<ExportPage />);
  await waitFor(() => expect(screen.getByLabelText("員工編號")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "下載 .xlsx" }));

  await waitFor(() => expect(screen.getByText("尚未指派所屬部門，無法匯出資料。")).toBeInTheDocument());
});

test("切換資料類型會重設欄位為新類型的完整欄位並清空預覽", async () => {
  mockGetExportPreview.mockResolvedValue({ columns: [{ key: "name", label: "姓名" }], rows: [["陳小華"]], total: 1 });
  render(<ExportPage />);
  await waitFor(() => expect(screen.getByLabelText("員工編號")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "預覽" }));
  await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());

  fireEvent.change(screen.getByLabelText("資料類型"), { target: { value: "attendance" } });

  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.getByLabelText("上班時間")).toBeChecked();
});

test("日期篩選欄位維持空白（不限日期），但點開日曆一律顯示展示用虛擬時鐘的今天所在月份", async () => {
  render(<ExportPage />);
  await waitFor(() => expect(screen.getByLabelText("資料類型")).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText("資料類型"), { target: { value: "attendance" } });
  await waitFor(() => expect(mockGetDemoClock).toHaveBeenCalled());

  expect(screen.getAllByRole("button", { name: "不限日期" })).toHaveLength(2);

  fireEvent.click(screen.getAllByRole("button", { name: "不限日期" })[0]);
  await waitFor(() => expect(screen.getByText("2026 年 8 月")).toBeInTheDocument());
});
