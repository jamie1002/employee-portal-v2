import { useEffect, useState } from "react";
import { getHealth } from "./api/health.api";

// 骨架階段的暫時畫面：驗證前後端連線與 design token 是否生效。
// 批 1 會換成真正的路由（AuthContext / ProtectedRoute）。
export default function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setError("無法連線到後端 API"));
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="glass-panel w-full max-w-sm rounded-xl p-6">
        <h1 className="text-lg font-medium text-text-primary">員工入口網站</h1>
        <p className="mt-1 text-sm text-text-secondary">專案骨架建置中</p>

        <div className="mt-4 rounded-lg border border-border-subtle bg-surface-900 p-3 text-sm">
          {error && <span className="text-status-danger">{error}</span>}
          {!error && !health && <span className="text-text-muted">檢查後端連線中…</span>}
          {health && (
            <span className="text-accent-400">
              API 狀態：{health.status}／資料庫：{health.database}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
