import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { markTodayNote } from "../api/attendance.api";
import PunchOutConfirmDialog from "./PunchOutConfirmDialog";
import TodayStatusCard from "./TodayStatusCard";

const MIN_OVERTIME_MS = 30 * 60 * 1000;

// 晚下班門檻不是前端寫死的「19 點」——那與正常工時結束時間無關（08:50 上班
// 18:50 下班已加班 30 分鐘卻不會跳出提示，19:05 下班卻一律跳出）。改用後端下班
// 打卡回應直接帶的 late_punch_out_threshold（＝正常工時結束時間 + 1 小時）。
function isLatePunchOut(attendance) {
  if (!attendance?.late_punch_out_threshold || !attendance?.punch_out_time) return false;
  return new Date(attendance.punch_out_time).getTime() >= new Date(attendance.late_punch_out_threshold).getTime();
}

// 加班是否值得顯示「前往申請」選項：後端下班打卡回應已直接帶 overtime_eligible_start
// （涵蓋浮動午休與請假交互影響），不需要前端重算一次午休、正常工時等邏輯。
function hasEnoughOvertime(attendance) {
  if (!attendance?.overtime_eligible_start || !attendance?.punch_out_time) return true;
  const diffMs = new Date(attendance.punch_out_time).getTime() - new Date(attendance.overtime_eligible_start).getTime();
  return diffMs >= MIN_OVERTIME_MS;
}

// today／onPunchIn／onPunchOut 由 DashboardPage 的 useAttendance() 提供，讓同一頁
// 的其他區塊（本月出勤總覽）能共用同一份「今日狀態」，不重複打 API。
// markTodayNote 是唯一的例外：純粹是下班後的附加備註，不影響 today 狀態本身，
// 故直接呼叫 API，不必透過 props 往返 DashboardPage。
export default function PunchPanel({ today, isLoading, isSubmitting, error, onPunchIn, onPunchOut }) {
  const navigate = useNavigate();
  const [lateAttendance, setLateAttendance] = useState(null);
  const [isMarkingNote, setIsMarkingNote] = useState(false);

  if (isLoading) {
    return <div className="glass-panel rounded-xl p-6 text-text-secondary">載入中…</div>;
  }

  const canPunchIn = !today?.has_punched_in;
  const canPunchOut = today?.has_punched_in && !today?.has_punched_out;

  // 下班打卡本身已經先完成（出勤紀錄已反映真實下班時間），這裡純粹是事後詢問
  // 「這段時間要不要順便去申請加班」，一律以後端回傳、由虛擬時鐘算出的值判斷，
  // 不依賴瀏覽器真實時間。
  async function handlePunchOutClick() {
    const attendance = await onPunchOut();
    if (attendance && isLatePunchOut(attendance)) {
      setLateAttendance(attendance);
    }
  }

  function handleApplyOvertime() {
    if (!lateAttendance) return;
    navigate("/requests/overtime/new", {
      state: {
        prefillStartTime: lateAttendance.overtime_eligible_start,
        prefillEndTime: lateAttendance.punch_out_time,
        prefillReason: "延遲下班加班申請",
      },
    });
    setLateAttendance(null);
  }

  async function handleMarkPersonalBusiness() {
    setIsMarkingNote(true);
    try {
      await markTodayNote();
    } catch {
      // 忽略：打卡本身已完成，備註只是附加資訊，失敗不阻擋使用者關閉彈窗。
    } finally {
      setIsMarkingNote(false);
      setLateAttendance(null);
    }
  }

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
            onClick={handlePunchOutClick}
            disabled={!canPunchOut || isSubmitting}
            className="flex-1 rounded-lg border border-accent-500 py-2 font-medium text-accent-400 hover:bg-surface-800 disabled:opacity-50"
          >
            {isSubmitting ? "處理中…" : "下班打卡"}
          </button>
        </div>
      </div>

      <TodayStatusCard today={today} />

      {lateAttendance && (
        <PunchOutConfirmDialog
          normalWorkEnd={lateAttendance.normal_work_end}
          onMarkPersonalBusiness={handleMarkPersonalBusiness}
          isMarkingNote={isMarkingNote}
          onApplyOvertime={handleApplyOvertime}
          canApplyOvertime={hasEnoughOvertime(lateAttendance)}
        />
      )}
    </div>
  );
}
