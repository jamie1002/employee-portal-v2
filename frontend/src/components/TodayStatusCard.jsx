import { formatTime } from "../utils/datetime";
import AttendanceStatusBadges from "./AttendanceStatusBadges";

export default function TodayStatusCard({ today }) {
  if (!today) return null;

  // 有紀錄時後端回傳 effective_* 生效欄位；完全沒有出勤列時退回原始欄位
  // （此時兩者本來就相同，皆為 null／false）。
  const status = today.effective_status ?? today.status;
  const punchInTime = today.effective_punch_in_time ?? today.punch_in_time;
  const punchOutTime = today.effective_punch_out_time ?? today.punch_out_time;
  const workHours = today.effective_work_hours ?? today.work_hours;
  const isEarlyLeave = today.effective_is_early_leave ?? today.is_early_leave;

  return (
    <div className="glass-panel rounded-xl p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-text-primary">今日出勤狀態</h3>
        <AttendanceStatusBadges
          status={status}
          isEarlyLeave={isEarlyLeave}
          isMissingPunchOut={today.is_missing_punch_out}
        />
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-4 text-sm">
        <div>
          <dt className="text-text-muted">上班時間</dt>
          <dd className="mt-1 text-text-primary">{formatTime(punchInTime)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">下班時間</dt>
          <dd className="mt-1 text-text-primary">{formatTime(punchOutTime)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">工時</dt>
          <dd className="mt-1 text-text-primary">{workHours ?? "—"}</dd>
        </div>
      </dl>

      {!today.has_punched_in && <p className="mt-4 text-sm text-text-secondary">今日尚未打卡。</p>}
    </div>
  );
}
