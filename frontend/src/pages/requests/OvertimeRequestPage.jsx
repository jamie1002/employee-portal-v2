import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { createOvertimeRequest } from "../../api/requests.api";

// 下班打卡較晚時，PunchOutConfirmDialog 選擇「申請加班」會帶著已完成打卡的
// overtime_eligible_start／punch_out_time 導到這裡，直接預填表單（見 PunchPanel.jsx）。
function splitDateTime(isoString) {
  if (!isoString) return { date: "", time: "" };
  const d = new Date(isoString);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
    .formatToParts(d)
    .reduce((acc, part) => ({ ...acc, [part.type]: part.value }), {});
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour === "24" ? "00" : parts.hour}:${parts.minute}`,
  };
}

const inputClass =
  "rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

export default function OvertimeRequestPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const prefillStart = splitDateTime(location.state?.prefillStartTime);
  const prefillEnd = splitDateTime(location.state?.prefillEndTime);

  const [startDate, setStartDate] = useState(prefillStart.date);
  const [startTime, setStartTime] = useState(prefillStart.time);
  const [endDate, setEndDate] = useState(prefillEnd.date);
  const [endTime, setEndTime] = useState(prefillEnd.time);
  const [reason, setReason] = useState(location.state?.prefillReason ?? "");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmitting) return;

    setIsSubmitting(true);
    setError("");
    try {
      await createOvertimeRequest({
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
      <h2 className="text-xl font-medium text-text-primary">加班申請</h2>

      <form onSubmit={handleSubmit} className="glass-panel space-y-4 rounded-xl p-6">
        <p className="text-xs text-text-muted">時數以 30 分鐘為單位計算，不足 30 分鐘的部分不計入。</p>
        {error && <p className="text-sm text-status-danger">{error}</p>}

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
              value={startTime}
              onChange={(event) => setStartTime(event.target.value)}
              className={inputClass}
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
              value={endTime}
              onChange={(event) => setEndTime(event.target.value)}
              className={inputClass}
            />
          </div>
        </div>

        <div>
          <label htmlFor="reason" className="mb-1 block text-xs text-text-muted">
            加班事由
          </label>
          <textarea
            id="reason"
            required
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className={`w-full ${inputClass}`}
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
