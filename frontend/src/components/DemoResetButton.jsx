import { useState } from "react";
import { resetDemoData } from "../api/demo.api";
import { useAuth } from "../context/AuthContext";

export default function DemoResetButton() {
  const { logout } = useAuth();
  const [isConfirming, setIsConfirming] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [error, setError] = useState("");

  async function handleConfirm() {
    setIsResetting(true);
    setError("");
    try {
      await resetDemoData();
      // 重置後帳號密碼、is_first_login 等狀態都回到種子狀態，強制登出讓
      // 使用者重新登入，不嘗試用本地已過期的使用者狀態接續操作。
      logout();
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "重置失敗，請稍後再試。");
      setIsResetting(false);
      setIsConfirming(false);
    }
  }

  if (isConfirming) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className="text-status-danger">確定要清空並重新載入所有展示資料？</span>
        <button
          type="button"
          disabled={isResetting}
          onClick={handleConfirm}
          className="rounded-lg bg-status-danger px-2 py-1 font-medium text-surface-950 disabled:opacity-50"
        >
          {isResetting ? "重置中…" : "確定重置"}
        </button>
        <button
          type="button"
          onClick={() => setIsConfirming(false)}
          className="rounded-lg border border-border-subtle px-2 py-1 text-text-secondary"
        >
          取消
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-xs text-status-danger">{error}</span>}
      <button
        type="button"
        onClick={() => setIsConfirming(true)}
        className="text-sm text-text-secondary hover:text-status-danger"
      >
        重置展示資料
      </button>
    </div>
  );
}
