import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createPunchRequest } from "../../api/requests.api";

function toIso(date, time) {
  if (!date || !time) return undefined;
  return `${date}T${time}:00+08:00`;
}

const inputClass =
  "rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

export default function PunchRequestPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // 首頁異常通知的補打卡連結帶 ?date= 預填申請日期（見 MonthlyAttendanceSummary）。
  const [type, setType] = useState("in");
  const [targetDate, setTargetDate] = useState(searchParams.get("date") ?? "");
  const [inTime, setInTime] = useState("");
  const [outTime, setOutTime] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const showIn = type === "in" || type === "both";
  const showOut = type === "out" || type === "both";

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmitting) return;

    setIsSubmitting(true);
    setError("");
    try {
      await createPunchRequest({
        type,
        target_date: targetDate,
        requested_in_time: showIn ? toIso(targetDate, inTime) : undefined,
        requested_out_time: showOut ? toIso(targetDate, outTime) : undefined,
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
      <h2 className="text-xl font-medium text-text-primary">補打卡申請</h2>

      <form onSubmit={handleSubmit} className="glass-panel space-y-4 rounded-xl p-6">
        {error && <p className="text-sm text-status-danger">{error}</p>}

        <div>
          <label htmlFor="type" className="mb-1 block text-xs text-text-muted">
            類型
          </label>
          <select id="type" value={type} onChange={(event) => setType(event.target.value)} className={inputClass}>
            <option value="in">補上班卡</option>
            <option value="out">補下班卡</option>
            <option value="both">補上下班卡</option>
          </select>
        </div>

        <div>
          <label htmlFor="target-date" className="mb-1 block text-xs text-text-muted">
            日期
          </label>
          <input
            id="target-date"
            type="date"
            required
            value={targetDate}
            onChange={(event) => setTargetDate(event.target.value)}
            className={inputClass}
          />
        </div>

        {showIn && (
          <div>
            <label htmlFor="in-time" className="mb-1 block text-xs text-text-muted">
              上班時間
            </label>
            <input
              id="in-time"
              type="time"
              required
              value={inTime}
              onChange={(event) => setInTime(event.target.value)}
              className={inputClass}
            />
          </div>
        )}

        {showOut && (
          <div>
            <label htmlFor="out-time" className="mb-1 block text-xs text-text-muted">
              下班時間
            </label>
            <input
              id="out-time"
              type="time"
              required
              value={outTime}
              onChange={(event) => setOutTime(event.target.value)}
              className={inputClass}
            />
          </div>
        )}

        <div>
          <label htmlFor="reason" className="mb-1 block text-xs text-text-muted">
            申請理由
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
