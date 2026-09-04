import LeaveQuotaSummary from "../components/LeaveQuotaSummary";
import MonthlyAttendanceSummary from "../components/MonthlyAttendanceSummary";
import PunchPanel from "../components/PunchPanel";
import { useAuth } from "../context/AuthContext";
import { useAttendance } from "../hooks/useAttendance";

export default function DashboardPage() {
  const { user } = useAuth();
  const { today, isLoading, isSubmitting, error, punchIn, punchOut } = useAttendance();

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-xl p-6">
        <h2 className="text-xl font-medium text-text-primary">{user.name}，你好</h2>
        <p className="mt-1 text-sm text-text-secondary">
          今天是 {today?.punch_date ?? "—"}
          {today?.is_workday === false && "（非上班日）"}
        </p>
      </div>

      <PunchPanel
        today={today}
        isLoading={isLoading}
        isSubmitting={isSubmitting}
        error={error}
        onPunchIn={punchIn}
        onPunchOut={punchOut}
      />

      <MonthlyAttendanceSummary
        punchDate={today?.punch_date}
        refreshKey={`${today?.has_punched_in}-${today?.has_punched_out}`}
      />

      <LeaveQuotaSummary />
    </div>
  );
}
