import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import ProtectedRoute from "./components/ProtectedRoute";
import AttendancePage from "./pages/AttendancePage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import DashboardPage from "./pages/DashboardPage";
import LeaveBalancePage from "./pages/LeaveBalancePage";
import LoginPage from "./pages/LoginPage";
import DepartmentPage from "./pages/admin/DepartmentPage";
import EmployeePage from "./pages/admin/EmployeePage";
import HolidayManagementPage from "./pages/admin/HolidayManagementPage";
import SchemaPage from "./pages/admin/SchemaPage";
import SettingsPage from "./pages/admin/SettingsPage";
import LeaveRequestPage from "./pages/requests/LeaveRequestPage";
import MyRequestsPage from "./pages/requests/MyRequestsPage";
import OvertimeRequestPage from "./pages/requests/OvertimeRequestPage";
import PunchRequestPage from "./pages/requests/PunchRequestPage";
import ReviewCenterPage from "./pages/review/ReviewCenterPage";
import VenueBookingPage from "./pages/VenueBookingPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        {/* 改密碼頁在 ProtectedRoute 內、但刻意不在 AppShell 內：
            強制改密碼時不該讓使用者從側邊欄溜到其他頁面。 */}
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/attendance" element={<AttendancePage />} />
          <Route path="/leave-balance" element={<LeaveBalancePage />} />
          <Route path="/requests" element={<MyRequestsPage />} />
          <Route path="/requests/punch/new" element={<PunchRequestPage />} />
          <Route path="/requests/leave/new" element={<LeaveRequestPage />} />
          <Route path="/requests/overtime/new" element={<OvertimeRequestPage />} />
          <Route path="/approvals" element={<ReviewCenterPage />} />
          <Route path="/venue" element={<VenueBookingPage />} />
          <Route path="/employees" element={<EmployeePage />} />
          <Route path="/departments" element={<DepartmentPage />} />
          <Route path="/holidays" element={<HolidayManagementPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/schema" element={<SchemaPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
