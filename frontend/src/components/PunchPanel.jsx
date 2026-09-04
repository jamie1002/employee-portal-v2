import TodayStatusCard from "./TodayStatusCard";

// 純呈現元件：資料與動作由 DashboardPage 的 useAttendance() 提供，
// 讓同一頁的其他區塊（本月出勤總覽）能共用同一份「今日狀態」，不重複打 API。
export default function PunchPanel({ today, isLoading, isSubmitting, error, onPunchIn, onPunchOut }) {
  if (isLoading) {
    return <div className="glass-panel rounded-xl p-6 text-text-secondary">載入中…</div>;
  }

  const canPunchIn = !today?.has_punched_in;
  const canPunchOut = today?.has_punched_in && !today?.has_punched_out;

  return (
    <div className="space-y-4">
      {today?.is_workday === false && (
        <div className="glass-panel rounded-xl border-purple-400/40 p-4 text-sm text-purple-300">
          今天是非上班日，這段時間若要認列加班，記得另外送出加班申請。
        </div>
      )}

      <div className="glass-panel rounded-xl p-6">
        {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onPunchIn}
            disabled={!canPunchIn || isSubmitting}
            className="flex-1 rounded-lg bg-accent-500 py-2 font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
          >
            {isSubmitting ? "處理中…" : "上班打卡"}
          </button>
          <button
            type="button"
            onClick={onPunchOut}
            disabled={!canPunchOut || isSubmitting}
            className="flex-1 rounded-lg border border-accent-500 py-2 font-medium text-accent-400 hover:bg-surface-800 disabled:opacity-50"
          >
            {isSubmitting ? "處理中…" : "下班打卡"}
          </button>
        </div>
      </div>

      <TodayStatusCard today={today} />
    </div>
  );
}
