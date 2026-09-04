export const STATUS_LABEL = {
  normal: "正常",
  late: "遲到",
  absent: "缺勤",
  holiday_work: "假日出勤",
  on_leave: "請假",
};

export const STATUS_CLASS = {
  normal: "text-status-normal border-status-normal",
  late: "text-status-late border-status-late",
  absent: "text-status-danger border-status-danger",
  holiday_work: "text-purple-400 border-purple-400",
  on_leave: "text-blue-400 border-blue-400",
};

// 出勤狀態徽章的共用呈現規則，供 TodayStatusCard 與 AttendanceTable 共用。
//
// `normal` 與早退／未打下班卡並存時**不顯示「正常」徽章**——同時掛「正常」和
// 「早退」會讓人無法判斷這天到底算不算異常。其餘狀態（遲到、缺勤）不受影響，
// 可以與早退並列（例如「遲到」＋「早退」本來就可能同時成立）。
export default function AttendanceStatusBadges({ status, isEarlyLeave = false, isMissingPunchOut = false }) {
  const showStatusBadge = status && !(status === "normal" && (isEarlyLeave || isMissingPunchOut));

  return (
    <span className="flex flex-wrap gap-1">
      {showStatusBadge && (
        <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_CLASS[status] ?? ""}`}>
          {STATUS_LABEL[status] ?? status}
        </span>
      )}
      {isEarlyLeave && (
        <span className="rounded-full border border-status-late px-2 py-0.5 text-xs text-status-late">
          早退
        </span>
      )}
      {isMissingPunchOut && (
        <span className="rounded-full border border-status-danger px-2 py-0.5 text-xs text-status-danger">
          未打下班卡
        </span>
      )}
    </span>
  );
}
