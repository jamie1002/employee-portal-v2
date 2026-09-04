import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import DemoResetButton from "./DemoResetButton";

const mockResetDemoData = vi.hoisted(() => vi.fn());
vi.mock("../api/demo.api", () => ({
  resetDemoData: (...args) => mockResetDemoData(...args),
}));

const mockLogout = vi.hoisted(() => vi.fn());
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ logout: mockLogout }),
}));

beforeEach(() => {
  mockResetDemoData.mockReset();
  mockLogout.mockReset();
});

test("點擊後需要二次確認才會呼叫 API", () => {
  render(<DemoResetButton />);

  fireEvent.click(screen.getByRole("button", { name: "重置展示資料" }));

  expect(mockResetDemoData).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "確定重置" })).toBeInTheDocument();
});

test("確認後呼叫 API 並登出", async () => {
  mockResetDemoData.mockResolvedValue({});
  render(<DemoResetButton />);
  fireEvent.click(screen.getByRole("button", { name: "重置展示資料" }));

  fireEvent.click(screen.getByRole("button", { name: "確定重置" }));

  await waitFor(() => expect(mockResetDemoData).toHaveBeenCalled());
  await waitFor(() => expect(mockLogout).toHaveBeenCalled());
});

test("取消不會呼叫 API，回到初始狀態", () => {
  render(<DemoResetButton />);
  fireEvent.click(screen.getByRole("button", { name: "重置展示資料" }));

  fireEvent.click(screen.getByRole("button", { name: "取消" }));

  expect(screen.getByRole("button", { name: "重置展示資料" })).toBeInTheDocument();
  expect(mockResetDemoData).not.toHaveBeenCalled();
});

test("失敗時顯示錯誤訊息且不登出", async () => {
  mockResetDemoData.mockRejectedValue({ response: { data: { error: { message: "權限不足" } } } });
  render(<DemoResetButton />);
  fireEvent.click(screen.getByRole("button", { name: "重置展示資料" }));

  fireEvent.click(screen.getByRole("button", { name: "確定重置" }));

  await waitFor(() => expect(screen.getByText("權限不足")).toBeInTheDocument());
  expect(mockLogout).not.toHaveBeenCalled();
});
