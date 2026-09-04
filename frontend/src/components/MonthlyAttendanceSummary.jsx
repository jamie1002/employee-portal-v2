import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMyRecords } from "../api/attendance.api";
import { getMyLeaveRequests, getMyOvertimeRequests, getMyPunchRequests } from "../api/requests.api";
import { formatDateTime, formatTime, monthRangeOf } from "../utils/datetime";
import AttendanceStatusBadges from "./AttendanceStatusBadges";

const PUNCH_TYPE_LABEL = { in: "補上班卡", out: "補下班卡", both: "補上下班卡" };

function isAbnormal(record) {
  return (
    record.effective_status === "late" ||
    record.effective_status === "absent" ||
    record.effective_is_early_leave ||
    record.is_missing_punch_out
  );
}

// 該日是否已有「待審核」的補打卡或請假申請涵蓋——已核准的申請會直接反映在生效
// 狀態上（該日屆時就不會再是異常），故這裡只需比對 pending 狀態即可。
function hasPendingRequestForDate(date, punchRequests, leaveRequests) {
  const pendingPunch = punchRequests.some((r) => r.target_date === date && r.status === "pending");
  if (pendingPunch) return true;

  return leaveRequests.some((r) => {
    if (r.status !== "pending") return false;
    return date >= r.start_time.slice(0, 10) && date <= r.end_time.slice(0, 10);
  });
}

// 補打卡申請的日期／時間／狀態文字格式統一成「MM/DD HH:mm　類型申請」（both
// 類型顯示上下班時間區間），與請假／加班的「MM/DD HH:mm ~ HH:mm　類型申請」
// 同一套視覺節奏，不要日期沒有時間、時間又沒有日期地兜出兩種不同格式。
function punchRequestDetail(r) {
  const label = `${PUNCH_TYPE_LABEL[r.type] ?? "補打卡"}申請`;
  if (r.type === "both") {
    return `${formatDateTime(r.requested_in_time)} ~ ${formatTime(r.requested_out_time)}　${label}`;
  }
  return `${formatDateTime(r.requested_in_time ?? r.requested_out_time)}　${label}`;
}

function buildPendingItems(punchRequests, leaveRequests, overtimeRequests) {
  const items = [
    ...punchRequests
      .filter((r) => r.status === "pending")
      .map((r) => ({
        key: `punch-${r.id}`,
        detail: punchRequestDetail(r),
        submittedAt: r.created_at,
      })),
    ...leaveRequests
      .filter((r) => r.status === "pending")
      .map((r) => ({
        key: `leave-${r.id}`,
        detail: `${formatDateTime(r.start_time)} ~ ${formatTime(r.end_time)}　請假申請（${r.leave_type}）`,
        submittedAt: r.created_at,
      })),
    ...overtimeRequests
      .filter((r) => r.status === "pending")
      .map((r) => ({
        key: `overtime-${r.id}`,
        detail: `${formatDateTime(r.start_time)} ~ ${formatTime(r.end_time)}　加班申請`,
        submittedAt: r.created_at,
      })),
  ];
  return items.sort((a, b) => new Date(b.submittedAt) - new Date(a.submittedAt));
}

// 本月出勤總覽：異常日（遲到／缺勤／早退／未打下班卡）+ 補打卡／請假快捷連結
// + 三種申請單的「申請中」清單。月份以**後端回傳的營業日**推算，不用 new Date()
// ——系統的今天是虛擬時鐘。
//
// `refreshKey` 由呼叫端帶入「今天的打卡狀態」：剛打完下班卡而且早退時，這張卡
// 必須跟著更新，否則畫面會出現「今天早退」與「本月沒有異常」自相矛盾的並列。
// 刻意收字串而不是整個 today 物件——相依項放會變動的物件會每次 render 都重打 API
// （見 docs/PITFALLS.md D2）。
export default function MonthlyAttendanceSummary({ punchDate, refreshKey }) {
  const [records, setRecords] = useState([]);
  const [punchRequests, setPunchRequests] = useState([]);
  const [leaveRequests, setLeaveRequests] = useState([]);
  const [overtimeRequests, setOvertimeRequests] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!punchDate) return undefined;

    let cancelled = false;
    const { startDate, endDate } = monthRangeOf(punchDate);
    setIsLoading(true);
    Promise.all([
      getMyRecords({ start_date: startDate, end_date: endDate, page: 1, page_size: 100 }),
      getMyPunchRequests(),
      getMyLeaveRequests(),
      getMyOvertimeRequests(),
    ])
      .then(([attendanceData, punchData, leaveData, overtimeData]) => {
        if (cancelled) return;
        setRecords(attendanceData.records.filter(isAbnormal));
        setPunchRequests(punchData.requests);
        setLeaveRequests(leaveData.requests);
        setOvertimeRequests(overtimeData.requests);
      })
      .catch(() => {
        if (!cancelled) {
          setRecords([]);
          setPunchRequests([]);
          setLeaveRequests([]);
          setOvertimeRequests([]);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [punchDate, refreshKey]);

  const pendingItems = buildPendingItems(punchRequests, leaveRequests, overtimeRequests);
  const unhandledCount = records.filter(
    (record) => !hasPendingRequestForDate(record.punch_date, punchRequests, leaveRequests),
  ).length;

  return (
    <div className="glass-panel rounded-xl p-6">
      <h3 className="text-lg font-medium text-text-primary">本月出勤總覽</h3>

      {!isLoading && unhandledCount > 0 && (
        <p className="mt-1 text-sm text-status-danger">本月有 {unhandledCount} 天異常未處理。</p>
      )}

      {isLoading && <p className="mt-3 text-sm text-text-secondary">載入中…</p>}

      {!isLoading && records.length === 0 && (
        <p className="mt-3 text-sm text-text-secondary">本月沒有異常出勤紀錄。</p>
      )}

      {!isLoading && records.length > 0 && (
        <ul className="mt-3 space-y-2">
          {records.map((record) => {
            const alreadyApplied = hasPendingRequestForDate(record.punch_date, punchRequests, leaveRequests);
            return (
              <li
                key={record.punch_date}
                className="flex items-center justify-between rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm"
              >
                <span className="flex items-center gap-2">
                  <span className="text-text-primary">{record.punch_date}</span>
                  <AttendanceStatusBadges
                    status={record.effective_status}
                    isEarlyLeave={record.effective_is_early_leave}
                    isMissingPunchOut={record.is_missing_punch_out}
                  />
                </span>
                {alreadyApplied ? (
                  <span className="text-text-muted">已申請，待審核</span>
                ) : (
                  <span className="flex gap-3">
                    <Link to={`/requests/punch/new?date=${record.punch_date}`} className="text-accent-400 hover:underline">
                      補打卡
                    </Link>
                    <Link to={`/requests/leave/new?date=${record.punch_date}`} className="text-accent-400 hover:underline">
                      請假
                    </Link>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {pendingItems.length > 0 && (
        <div className="mt-4 border-t border-border-subtle pt-4">
          <p className="text-sm font-medium text-text-primary">申請中（{pendingItems.length}）</p>
          <ul className="mt-2 space-y-1">
            {pendingItems.map((item) => (
              <li key={item.key} className="flex items-center justify-between text-sm text-text-secondary">
                <span>{item.detail}</span>
                <span className="text-text-muted">送出：{formatDateTime(item.submittedAt)}</span>
              </li>
            ))}
          </ul>
          <Link to="/requests" className="mt-2 inline-block text-sm text-accent-400 hover:underline">
            查看我的申請
          </Link>
        </div>
      )}
    </div>
  );
}
