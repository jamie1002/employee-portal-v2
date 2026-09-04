import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import ProtectedRoute from "./ProtectedRoute";

const mockUseAuth = vi.fn();
vi.mock("../context/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderWithRouter(initialPath, authState) {
  mockUseAuth.mockReturnValue(authState);
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div>登入頁</div>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/change-password" element={<div>改密碼頁</div>} />
          <Route path="/" element={<div>首頁</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

test("isLoading 時顯示載入中，不做任何導頁判斷", () => {
  renderWithRouter("/", { user: null, isLoading: true });
  expect(screen.getByText("載入中…")).toBeInTheDocument();
});

test("未登入導向登入頁", () => {
  renderWithRouter("/", { user: null, isLoading: false });
  expect(screen.getByText("登入頁")).toBeInTheDocument();
});

test("is_first_login 為真時強制導向改密碼頁", () => {
  renderWithRouter("/", { user: { is_first_login: true }, isLoading: false });
  expect(screen.getByText("改密碼頁")).toBeInTheDocument();
});

test("is_first_login 為真但已經在改密碼頁時不重複導頁", () => {
  renderWithRouter("/change-password", { user: { is_first_login: true }, isLoading: false });
  expect(screen.getByText("改密碼頁")).toBeInTheDocument();
});

test("正常登入時渲染子路由", () => {
  renderWithRouter("/", { user: { is_first_login: false }, isLoading: false });
  expect(screen.getByText("首頁")).toBeInTheDocument();
});
