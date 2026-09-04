import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

// 展示帳號固定密碼（見 SPEC.md §1）。刻意不是元件狀態，避免被寫進
// type="password" 欄位的 state（見下方 handleQuickLogin 的說明）。
const DEMO_PASSWORD = "Demo1234";

const DEMO_ACCOUNTS = [
  { icon: "👑", label: "管理者 Admin", email: "admin@demo.com" },
  { icon: "📋", label: "部門主管 Manager", email: "manager@demo.com" },
  { icon: "💻", label: "一般員工 Employee", email: "employee@demo.com" },
];

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // useRef 做「檢查並設定」：useState 的更新不會在同一個事件迴圈內同步生效，
  // 快速連點仍可能在 setIsSubmitting(true) 生效前重複觸發送出。
  const isSubmittingRef = useRef(false);

  async function performLogin(loginEmail, loginPassword) {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setError(null);

    try {
      await login(loginEmail, loginPassword);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "登入失敗，請稍後再試。");
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    performLogin(email, password);
  }

  function handleQuickLogin(demoEmail) {
    // 刻意不呼叫 setPassword(DEMO_PASSWORD)：Chrome 會把「密碼欄曾有值 + 表單卸載」
    // 判定為透過 JS 完成的登入，跳出「記住密碼」提示（見 docs/UI-SPEC.md §3.2）。
    setEmail(demoEmail);
    performLogin(demoEmail, DEMO_PASSWORD);
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-md space-y-4">
        <div className="glass-panel rounded-xl p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h1 className="text-lg font-medium text-text-primary">Employee Portal</h1>
              <p className="text-sm text-text-secondary">企業員工管理與出勤系統</p>
            </div>
          </div>

          <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
            <div>
              <label className="mb-1 block text-sm text-text-secondary" htmlFor="email">
                電子郵件
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                className="w-full rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-text-primary focus:border-accent-500 focus:outline-none disabled:opacity-50"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={isSubmitting}
                required
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-text-secondary" htmlFor="password">
                密碼
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className="w-full rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-text-primary focus:border-accent-500 focus:outline-none disabled:opacity-50"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={isSubmitting}
                required
              />
            </div>

            {error && <p className="text-sm text-status-danger">{error}</p>}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-lg bg-accent-500 py-2 font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
            >
              登入
            </button>
          </form>
        </div>

        <div className="glass-panel rounded-xl p-4">
          <p className="mb-2 text-xs text-text-muted">一鍵代入測試帳號（展示環境所有訪客共用，密碼固定）</p>
          <div className="space-y-2">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                type="button"
                disabled={isSubmitting}
                onClick={() => handleQuickLogin(account.email)}
                className="flex w-full items-center justify-between rounded-lg border border-border-subtle px-3 py-2 text-sm text-text-secondary hover:border-accent-500 hover:text-text-primary disabled:opacity-50"
              >
                <span>
                  {account.icon} {account.label}
                </span>
                <span className="text-text-muted">{account.email}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
