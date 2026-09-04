import { useEffect, useState } from "react";
import { getSettings, updateSettings } from "../../api/settings.api";
import RoleGate from "../../components/RoleGate";

const inputClass =
  "rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

// 後端 TIME 欄位序列化含秒（"09:00:00"），<input type="time"> 只吃 "HH:mm"。
function toInputTime(value) {
  return value ? value.slice(0, 5) : "";
}

function SettingsContent() {
  const [workStart, setWorkStart] = useState("");
  const [workEnd, setWorkEnd] = useState("");
  const [lunchStart, setLunchStart] = useState("");
  const [lunchEnd, setLunchEnd] = useState("");
  const [gracePeriod, setGracePeriod] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function applySettings(settings) {
    setWorkStart(toInputTime(settings.work_start_time));
    setWorkEnd(toInputTime(settings.work_end_time));
    setLunchStart(toInputTime(settings.lunch_start_time));
    setLunchEnd(toInputTime(settings.lunch_end_time));
    setGracePeriod(settings.grace_period_minutes);
  }

  useEffect(() => {
    getSettings().then(({ settings }) => {
      applySettings(settings);
      setIsLoading(false);
    });
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccessMessage("");

    if (!(workStart < lunchStart && lunchStart < lunchEnd && lunchEnd < workEnd)) {
      setError("考勤時段設定不合理，須符合「上班 < 午休開始 < 午休結束 < 下班」。");
      return;
    }

    setIsSubmitting(true);
    try {
      const { settings } = await updateSettings({
        work_start_time: workStart,
        work_end_time: workEnd,
        lunch_start_time: lunchStart,
        lunch_end_time: lunchEnd,
        grace_period_minutes: Number(gracePeriod),
      });
      applySettings(settings);
      setSuccessMessage("設定已更新");
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "更新失敗，請稍後再試。");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return <p className="text-sm text-text-muted">載入中…</p>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">考勤設定</h2>
      <p className="text-sm text-text-muted">修改僅影響後續打卡，不回溯重算歷史紀錄。</p>

      <form onSubmit={handleSubmit} className="glass-panel space-y-4 rounded-xl p-6">
        {error && <p className="text-sm text-status-danger">{error}</p>}
        {successMessage && <p className="text-sm text-accent-400">{successMessage}</p>}

        <div className="flex flex-wrap gap-4">
          <div>
            <label htmlFor="work-start" className="mb-1 block text-xs text-text-muted">
              上班時間
            </label>
            <input id="work-start" type="time" required value={workStart} onChange={(e) => setWorkStart(e.target.value)} className={inputClass} />
          </div>
          <div>
            <label htmlFor="work-end" className="mb-1 block text-xs text-text-muted">
              下班時間
            </label>
            <input id="work-end" type="time" required value={workEnd} onChange={(e) => setWorkEnd(e.target.value)} className={inputClass} />
          </div>
        </div>

        <div className="flex flex-wrap gap-4">
          <div>
            <label htmlFor="lunch-start" className="mb-1 block text-xs text-text-muted">
              午休開始
            </label>
            <input id="lunch-start" type="time" required value={lunchStart} onChange={(e) => setLunchStart(e.target.value)} className={inputClass} />
          </div>
          <div>
            <label htmlFor="lunch-end" className="mb-1 block text-xs text-text-muted">
              午休結束
            </label>
            <input id="lunch-end" type="time" required value={lunchEnd} onChange={(e) => setLunchEnd(e.target.value)} className={inputClass} />
          </div>
        </div>

        <div>
          <label htmlFor="grace-period" className="mb-1 block text-xs text-text-muted">
            緩衝時間（分鐘）
          </label>
          <input
            id="grace-period" type="number" min={0} max={240} required value={gracePeriod}
            onChange={(e) => setGracePeriod(e.target.value)} className={inputClass}
          />
          <p className="mt-1 text-xs text-text-muted">
            同時作為遲到寬限與提早到班的工時起算基準（雙向），但早退判定不適用此緩衝。
          </p>
        </div>

        <button
          type="submit" disabled={isSubmitting}
          className="rounded-lg bg-accent-500 px-4 py-2 font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
        >
          {isSubmitting ? "儲存中…" : "儲存設定"}
        </button>
      </form>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <RoleGate roles={["admin"]} permissions={["settings.manage"]}>
      <SettingsContent />
    </RoleGate>
  );
}
