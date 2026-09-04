import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import LoginPage from "./LoginPage";

const mockLogin = vi.fn();
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ login: mockLogin }),
}));

function renderLoginPage() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockLogin.mockReset();
});

test("送出表單時用輸入欄位的值呼叫 login()", async () => {
  mockLogin.mockResolvedValue({});
  renderLoginPage();

  fireEvent.change(screen.getByLabelText("電子郵件"), { target: { value: "admin@demo.com" } });
  fireEvent.change(screen.getByLabelText("密碼"), { target: { value: "Demo1234" } });
  fireEvent.click(screen.getByRole("button", { name: "登入" }));

  await vi.waitFor(() => expect(mockLogin).toHaveBeenCalledWith("admin@demo.com", "Demo1234"));
});

test("一鍵代入不會把密碼寫進 password 欄位的 state", async () => {
  mockLogin.mockResolvedValue({});
  renderLoginPage();

  fireEvent.click(screen.getByRole("button", { name: /一般員工 Employee/ }));

  await vi.waitFor(() => expect(mockLogin).toHaveBeenCalledWith("employee@demo.com", "Demo1234"));
  expect(screen.getByLabelText("密碼").value).toBe("");
  expect(screen.getByLabelText("電子郵件").value).toBe("employee@demo.com");
});

test("登入失敗時顯示後端回傳的錯誤訊息", async () => {
  mockLogin.mockRejectedValue({ response: { data: { error: { message: "電子郵件或密碼錯誤。" } } } });
  renderLoginPage();

  fireEvent.click(screen.getByRole("button", { name: /管理者 Admin/ }));

  expect(await screen.findByText("電子郵件或密碼錯誤。")).toBeInTheDocument();
});

test("重複點擊一鍵代入時只送出一次請求", async () => {
  let resolveLogin;
  mockLogin.mockReturnValue(
    new Promise((resolve) => {
      resolveLogin = resolve;
    }),
  );
  renderLoginPage();

  const button = screen.getByRole("button", { name: /管理者 Admin/ });
  fireEvent.click(button);
  fireEvent.click(button);

  expect(mockLogin).toHaveBeenCalledTimes(1);
  resolveLogin({});
});
