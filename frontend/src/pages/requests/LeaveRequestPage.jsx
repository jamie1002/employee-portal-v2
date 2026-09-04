import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createLeaveRequest } from "../../api/requests.api";
import { getSettings } from "../../api/settings.api";

// 後端 TIME 欄位序列化含秒（"09:00:00"），<input type="time"> 只吃 "HH:mm"。
function toInputTime(value) {
  return value ? value.slice(0, 5) : "";
}

const LEAVE_TYPES = ["事假", "病假", "特別休假", "公假"];
// 特別休假（年假）是員工自己的權益假別，不強制填理由；其餘假別仍為必填（SPEC.md §4.3）。
const OPTIONAL_REASON_TYPE = "特別休假";

const inputClass =
  "w-full sm:w-auto rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

export default function LeaveRequestPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // 首頁異常通知的請假連結帶 ?date= 預填申請日期（見 MonthlyAttendanceSummary）。
  const prefilledDate = searchParams.get("date") ?? "";
  const [leaveType, setLeaveType] = useState(LEAVE_TYPES[0]);
  const [startDate, setStartDate] = useState(prefilledDate);
  const [startTime, setStartTime] = useState("");
  const [endDate, setEndDate] = useState(prefilledDate);
  const [endTime, setEndTime] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isFullDay, setIsFullDay] = useState(false);
  const [workHours, setWorkHours] = useState({ start: "", end: "" });

  const isReasonRequired = leaveType !== OPTIONAL_REASON_TYPE;

  useEffect(() => {
    getSettings().then(({ settings }) => {
      setWorkHours({ start: toInputTime(settings.work_start_time), end: toInputTime(settings.work_end_time) });
    });
  }, []);

  // 「整天」勾選框自動帶入表定上下班時間（UI-SPEC.md §3.8）；勾選期間時間欄位
  // 停用，避免使用者手動改動後跟畫面上的「整天」語意不一致。
  function handleFullDayChange(checked) {
    setIsFullDay(checked);
    if (checked) {
      setStartTime(workHours.start);
      setEndTime(workHours.end);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmitting) return;

    setIsSubmitting(true);
    setError("");
    try {
      await createLeaveRequest({
        leave_type: leaveType,
        start_time: `${startDate}T${startTime}:00+08:00`,
        end_time: `${endDate}T${endTime}:00+08:00`,
        reason,
      });
      navigate("/requests");
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "申請失敗，請稍後再試。");
      setIsSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">請假申請</h2>

      <form onSubmit={handleSubmit} className="glass-panel space-y-4 rounded-xl p-6">
        {error && <p className="text-sm text-status-danger">{error}</p>}

        <div>
          <label htmlFor="leave-type" className="mb-1 block text-xs text-text-muted">
            假別
          </label>
          <select
            id="leave-type"
            value={leaveType}
            onChange={(event) => setLeaveType(event.target.value)}
            className={inputClass}
          >
            {LEAVE_TYPES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>

        <label className="flex items-center gap-2 text-sm text-text-primary">
          <input
            type="checkbox"
            checked={isFullDay}
            onChange={(event) => handleFullDayChange(event.target.checked)}
            className="rounded border-border-subtle"
          />
          整天（自動帶入表定上下班時間 {workHours.start} ~ {workHours.end}）
        </label>

        <div className="flex flex-wrap gap-4">
          <div>
            <label htmlFor="start-date" className="mb-1 block text-xs text-text-muted">
              開始日期
            </label>
            <input
              id="start-date"
              type="date"
              required
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor="start-time" className="mb-1 block text-xs text-text-muted">
              開始時間
            </label>
            <input
              id="start-time"
              type="time"
              required
              disabled={isFullDay}
              value={startTime}
              onChange={(event) => setStartTime(event.target.value)}
              className={`${inputClass} disabled:opacity-50`}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-4">
          <div>
            <label htmlFor="end-date" className="mb-1 block text-xs text-text-muted">
              結束日期
            </label>
            <input
              id="end-date"
              type="date"
              required
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor="end-time" className="mb-1 block text-xs text-text-muted">
              結束時間
            </label>
            <input
              id="end-time"
              type="time"
              required
              disabled={isFullDay}
              value={endTime}
              onChange={(event) => setEndTime(event.target.value)}
              className={`${inputClass} disabled:opacity-50`}
            />
          </div>
        </div>

        <p className="text-xs text-text-muted">
          時數以逐工作日與表定工時的交集計算，跳過週末與國定假日；正式時數以送出後的後端回應為準。
        </p>

        <div>
          <label htmlFor="reason" className="mb-1 block text-xs text-text-muted">
            申請理由{!isReasonRequired && "（特別休假可不填）"}
          </label>
          <textarea
            id="reason"
            required={isReasonRequired}
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className={`${inputClass} !w-full`}
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-lg bg-accent-500 px-4 py-2 font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
        >
          {isSubmitting ? "送出中…" : "送出申請"}
        </button>
      </form>
    </div>
  );
}
