import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import * as authApi from "../api/auth.api";
import { AuthProvider, useAuth } from "./AuthContext";

vi.mock("../api/auth.api");

const mockClient = vi.hoisted(() => ({
  getStoredToken: vi.fn(),
  setStoredToken: vi.fn(),
  clearStoredToken: vi.fn(),
}));
vi.mock("../api/client", () => mockClient);

function Probe() {
  const { user, isLoading, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="user">{user ? user.email : "none"}</span>
      <button onClick={() => login("admin@demo.com", "Demo1234")}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

test("沒有已存 token 時直接結束載入，不呼叫 getMe", async () => {
  mockClient.getStoredToken.mockReturnValue(null);

  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );

  await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
  expect(authApi.getMe).not.toHaveBeenCalled();
  expect(screen.getByTestId("user").textContent).toBe("none");
});

test("已有 token 時掛載時呼叫 getMe 還原使用者", async () => {
  mockClient.getStoredToken.mockReturnValue("existing-token");
  authApi.getMe.mockResolvedValue({ user: { email: "admin@demo.com" } });

  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );

  await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("admin@demo.com"));
});

test("getMe 失敗時清掉本機憑證並維持未登入", async () => {
  mockClient.getStoredToken.mockReturnValue("stale-token");
  authApi.getMe.mockRejectedValue(new Error("401"));

  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );

  await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
  expect(mockClient.clearStoredToken).toHaveBeenCalled();
  expect(screen.getByTestId("user").textContent).toBe("none");
});

test("login() 成功後寫入 token 並更新 user 狀態", async () => {
  mockClient.getStoredToken.mockReturnValue(null);
  authApi.login.mockResolvedValue({ token: "new-token", user: { email: "admin@demo.com" } });

  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

  fireEvent.click(screen.getByText("login"));

  await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("admin@demo.com"));
  expect(mockClient.setStoredToken).toHaveBeenCalledWith("new-token");
});

test("logout() 清掉 token 並把 user 設回 null", async () => {
  mockClient.getStoredToken.mockReturnValue(null);
  authApi.login.mockResolvedValue({ token: "new-token", user: { email: "admin@demo.com" } });

  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

  fireEvent.click(screen.getByText("login"));
  await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("admin@demo.com"));

  fireEvent.click(screen.getByText("logout"));

  expect(screen.getByTestId("user").textContent).toBe("none");
  expect(mockClient.clearStoredToken).toHaveBeenCalled();
});
