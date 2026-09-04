import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ChangePasswordPage() {
  const { changePassword, logout, recentLoginPassword } = useAuth();
  const navigate = useNavigate();

  const [oldPassword, setOldPassword] = useState(recentLoginPassword ?? "");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();

    if (newPassword !== confirmPassword) {
      setError("兩次輸入的新密碼不一致。");
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      await changePassword(oldPassword, newPassword);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "修改密碼失敗，請稍後再試。");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleLogoutInstead() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="glass-panel w-full max-w-md rounded-xl p-6">
        <h1 className="text-lg font-medium text-text-primary">修改密碼</h1>
        <p className="mt-1 text-sm text-text-secondary">新密碼至少 8 碼，且需同時包含英文字母與數字。</p>

        <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-sm text-text-secondary" htmlFor="old-password">
              目前密碼
            </label>
            <input
              id="old-password"
              type="password"
              autoComplete="current-password"
              className="w-full rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-text-primary focus:border-accent-500 focus:outline-none disabled:opacity-50"
              value={oldPassword}
              onChange={(event) => setOldPassword(event.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-text-secondary" htmlFor="new-password">
              新密碼
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              className="w-full rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-text-primary focus:border-accent-500 focus:outline-none disabled:opacity-50"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-text-secondary" htmlFor="confirm-password">
              確認新密碼
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              className="w-full rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-text-primary focus:border-accent-500 focus:outline-none disabled:opacity-50"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
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
            確認修改
          </button>
        </form>

        <button
          type="button"
          onClick={handleLogoutInstead}
          className="mt-3 text-sm text-text-secondary hover:text-text-primary"
        >
          不想修改密碼？登出並換其他帳號
        </button>
      </div>
    </div>
  );
}
