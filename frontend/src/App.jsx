import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import LoginPage from "./pages/LoginPage";

// 批 2 起會把這個佔位頁換成真正的 AppShell + 首頁，這裡只證明
// 認證骨架（登入 → 導頁 → 受保護路由）跑得通。
function PlaceholderHome() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="glass-panel rounded-xl p-6 text-text-secondary">
        登入成功。首頁與版面骨架將於後續批次建置。
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route path="/" element={<PlaceholderHome />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
