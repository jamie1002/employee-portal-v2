import { useEffect, useState } from "react";
import { getMyRecords } from "../api/attendance.api";
import { monthRangeOf } from "../utils/datetime";
import AttendanceStatusBadges from "./AttendanceStatusBadges";

function isAbnormal(record) {
  return (
    record.effective_status === "late" ||
    record.effective_status === "absent" ||
    record.effective_is_early_leave ||
    record.is_missing_punch_out
  );
}

// 本月出勤總覽：只列異常日（遲到／缺勤／早退／未打下班卡）。
// 月份以**後端回傳的營業日**推算，不用 new Date()——系統的今天是虛擬時鐘。
//
// `refreshKey` 由呼叫端帶入「今天的打卡狀態」：剛打完下班卡而且早退時，這張卡
// 必須跟著更新，否則畫面會出現「今天早退」與「本月沒有異常」自相矛盾的並列。
// 刻意收字串而不是整個 today 物件——相依項放會變動的物件會每次 render 都重打 API
// （見 docs/PITFALLS.md D2）。
export default function MonthlyAttendanceSummary({ punchDate, refreshKey }) {
  const [records, setRecords] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!punchDate) return undefined;

    let cancelled = false;
    const { startDate, endDate } = monthRangeOf(punchDate);
    setIsLoading(true);
    getMyRecords({ start_date: startDate, end_date: endDate, page: 1, page_size: 100 })
      .then((data) => {
        if (!cancelled) setRecords(data.records.filter(isAbnormal));
      })
      .catch(() => {
        if (!cancelled) setRecords([]);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [punchDate, refreshKey]);

  return (
    <div className="glass-panel rounded-xl p-6">
      <h3 className="text-lg font-medium text-text-primary">本月出勤總覽</h3>

      {isLoading && <p className="mt-3 text-sm text-text-secondary">載入中…</p>}

      {!isLoading && records.length === 0 && (
        <p className="mt-3 text-sm text-text-secondary">本月沒有異常出勤紀錄。</p>
      )}

      {!isLoading && records.length > 0 && (
        <ul className="mt-3 space-y-2">
          {records.map((record) => (
            <li
              key={record.punch_date}
              className="flex items-center justify-between rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm"
            >
              <span className="text-text-primary">{record.punch_date}</span>
              <AttendanceStatusBadges
                status={record.effective_status}
                isEarlyLeave={record.effective_is_early_leave}
                isMissingPunchOut={record.is_missing_punch_out}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
