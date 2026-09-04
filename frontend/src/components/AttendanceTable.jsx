import { Fragment, useEffect, useState } from "react";
import { getAttendanceChanges } from "../api/attendanceChanges.api";
import { formatDateTime, formatTime, taipeiDateKey } from "../utils/datetime";
import AttendanceStatusBadges from "./AttendanceStatusBadges";

const REQUEST_STATUS_LABEL = { pending: "待審", approved: "已核准", rejected: "已駁回" };
const PUNCH_TYPE_LABEL = { in: "補上班卡", out: "補下班卡", both: "補上下班卡" };

function datesBetween(start, end) {
  const dates = [];
  const cursor = new Date(`${start}T00:00:00Z`);
  const last = new Date(`${end}T00:00:00Z`);
  while (cursor.getTime() <= last.getTime()) {
    dates.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return dates;
}

// 依 (user_id, 日期) 分組：補打卡精確比對目標日期；請假只要落在起訖區間內即算命中。
function groupChangesByUserAndDate(changes) {
  const grouped = new Map();
  for (const change of changes) {
    const dates =
      change.source === "punch_request"
        ? [change.start_date]
        : datesBetween(change.start_date, change.end_date);
    for (const date of dates) {
      const key = `${change.user_id}_${date}`;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(change);
    }
  }
  return grouped;
}

function formatLeavePeriod(change) {
  const sameDay = taipeiDateKey(change.leave_start_time) === taipeiDateKey(change.leave_end_time);
  const period = sameDay
    ? `${formatTime(change.leave_start_time)} - ${formatTime(change.leave_end_time)}`
    : `${formatDateTime(change.leave_start_time)} ~ ${formatDateTime(change.leave_end_time)}`;
  return `${period}（共 ${change.hours} 小時）`;
}

function ChangeEntry({ change }) {
  const detail =
    change.source === "punch_request"
      ? `${PUNCH_TYPE_LABEL[change.punch_type] ?? change.punch_type}${
          change.requested_in_time ? `　上班：${formatDateTime(change.requested_in_time)}` : ""
        }${change.requested_out_time ? `　下班：${formatDateTime(change.requested_out_time)}` : ""}`
      : `${change.leave_type}　${formatLeavePeriod(change)}`;

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-900/50 p-2 text-xs text-text-secondary">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-border-subtle px-2 py-0.5">
          {REQUEST_STATUS_LABEL[change.status] ?? change.status}
        </span>
        <span>{change.source === "punch_request" ? "補打卡申請" : "請假申請"}</span>
        <span>送出：{formatDateTime(change.submitted_at)}</span>
        {change.status !== "pending" && (
          <>
            <span>審核者：{change.reviewer_name ?? "—"}</span>
            <span>審核時間：{formatDateTime(change.reviewed_at)}</span>
          </>
        )}
      </div>
      <p className="mt-1 text-text-muted">{detail}</p>
      {change.status === "rejected" && change.review_note && (
        <p className="mt-1 text-status-danger">駁回備註：{change.review_note}</p>
      )}
    </div>
  );
}

export default function AttendanceTable({ records, showUser = false, filters }) {
  const [showChanges, setShowChanges] = useState(false);
  const [changesMap, setChangesMap] = useState(new Map());
  const [isLoadingChanges, setIsLoadingChanges] = useState(false);

  useEffect(() => {
    if (!showChanges || !records || records.length === 0) return undefined;

    let cancelled = false;
    const dates = records.map((record) => record.punch_date).sort();
    setIsLoadingChanges(true);
    getAttendanceChanges({ start_date: dates[0], end_date: dates[dates.length - 1], ...filters })
      .then((data) => {
        if (!cancelled) setChangesMap(groupChangesByUserAndDate(data.changes));
      })
      .catch(() => {
        if (!cancelled) setChangesMap(new Map());
      })
      .finally(() => {
        if (!cancelled) setIsLoadingChanges(false);
      });

    return () => {
      cancelled = true;
    };
  }, [showChanges, records, filters]);

  if (!records || records.length === 0) {
    return <div className="glass-panel rounded-xl p-8 text-center text-text-secondary">尚無出勤紀錄。</div>;
  }

  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm text-text-secondary">
        <input
          type="checkbox"
          checked={showChanges}
          onChange={(event) => setShowChanges(event.target.checked)}
          className="rounded border-border-subtle"
        />
        顯示異動{isLoadingChanges && "（載入中…）"}
      </label>

      <div className="glass-panel overflow-x-auto rounded-xl">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-text-muted">
              {showUser && <th className="px-4 py-3">姓名</th>}
              {showUser && <th className="px-4 py-3">部門</th>}
              <th className="px-4 py-3">日期</th>
              <th className="px-4 py-3">上班時間</th>
              <th className="px-4 py-3">下班時間</th>
              <th className="px-4 py-3">狀態</th>
              <th className="px-4 py-3">工時</th>
              <th className="px-4 py-3">備註</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => {
              const relatedChanges = showChanges
                ? changesMap.get(`${record.user_id}_${record.punch_date}`)
                : null;
              return (
                <Fragment key={`${record.user_id}_${record.punch_date}`}>
                  <tr className="border-b border-border-subtle last:border-0">
                    {showUser && <td className="px-4 py-3 text-text-primary">{record.user_name}</td>}
                    {showUser && (
                      <td className="px-4 py-3 text-text-secondary">{record.department_name ?? "—"}</td>
                    )}
                    <td className="px-4 py-3 text-text-primary">
                      {record.punch_date}
                      {/* has_changes 標在「日期」旁：這天有申請單（不論狀態）。 */}
                      {record.has_changes && (
                        <span
                          title="當天有補打卡或請假申請"
                          className="ml-1.5 rounded-full border border-border-strong px-1.5 py-0 text-[10px] text-text-secondary"
                        >
                          有異動申請
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {formatTime(record.effective_punch_in_time)}
                      {/* is_adjusted 標在「上班時間」旁：已核准且真的改動了生效值。 */}
                      {record.is_adjusted && (
                        <span className="ml-1.5 rounded-full border border-accent-500/60 px-1.5 py-0 text-[10px] text-accent-400">
                          已異動
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {formatTime(record.effective_punch_out_time)}
                    </td>
                    <td className="px-4 py-3">
                      <AttendanceStatusBadges
                        status={record.effective_status}
                        isEarlyLeave={record.effective_is_early_leave}
                        isMissingPunchOut={record.is_missing_punch_out}
                      />
                    </td>
                    <td className="px-4 py-3 text-text-primary">{record.effective_work_hours ?? "—"}</td>
                    <td className="px-4 py-3 text-text-secondary">{record.note ?? "—"}</td>
                  </tr>
                  {relatedChanges && relatedChanges.length > 0 && (
                    <tr className="border-b border-border-subtle bg-surface-800/30 last:border-0">
                      <td colSpan={showUser ? 8 : 6} className="space-y-1 px-4 py-2">
                        {relatedChanges.map((change) => (
                          <ChangeEntry key={`${change.source}-${change.request_id}`} change={change} />
                        ))}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
