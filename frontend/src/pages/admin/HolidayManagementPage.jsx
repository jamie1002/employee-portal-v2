import { useEffect, useRef, useState } from "react";
import { createHoliday, deleteHoliday, getHolidays } from "../../api/holidays.api";
import RoleGate from "../../components/RoleGate";
import { useVirtualToday } from "../../hooks/useVirtualClock";

const inputClass =
  "rounded-lg border border-border-subtle bg-surface-900 px-2 py-1 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

function insertSortedByDate(holidays, holiday) {
  const next = [...holidays, holiday];
  next.sort((a, b) => a.holiday_date.localeCompare(b.holiday_date));
  return next;
}

function CreateHolidayForm({ onCreated }) {
  const [holidayDate, setHolidayDate] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isSubmittingRef = useRef(false);

  // 日期欄位預設帶入展示用虛擬時鐘的今天，避免使用者點開日期選擇器時被瀏覽器
  // 原生 UI 帶到真實現在的月份（見 docs/PITFALLS.md B6）。
  const virtualToday = useVirtualToday();
  useEffect(() => {
    if (virtualToday && !holidayDate) setHolidayDate(virtualToday);
  }, [virtualToday, holidayDate]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setError("");
    try {
      const { holiday } = await createHoliday({ holiday_date: holidayDate, name });
      onCreated(holiday);
      setHolidayDate("");
      setName("");
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "新增失敗，請稍後再試。");
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="glass-panel flex flex-col items-stretch gap-3 rounded-xl p-4 sm:flex-row sm:flex-wrap sm:items-end">
      {error && <p className="w-full text-sm text-status-danger">{error}</p>}
      <div className="w-full sm:w-auto">
        <label htmlFor="holiday-date" className="mb-1 block text-xs text-text-muted">
          日期
        </label>
        <input
          id="holiday-date" type="date" required value={holidayDate}
          onChange={(e) => setHolidayDate(e.target.value)} className={`w-full sm:w-auto ${inputClass}`}
        />
      </div>
      <div className="w-full sm:w-auto">
        <label htmlFor="holiday-name" className="mb-1 block text-xs text-text-muted">
          名稱
        </label>
        <input
          id="holiday-name" required value={name} onChange={(e) => setName(e.target.value)}
          className={`w-full sm:w-auto ${inputClass}`}
        />
      </div>
      <button
        type="submit" disabled={isSubmitting}
        className="min-h-11 rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
      >
        {isSubmitting ? "新增中…" : "新增假日"}
      </button>
    </form>
  );
}

function HolidayContent() {
  const [holidays, setHolidays] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getHolidays().then(({ holidays: rows }) => {
      setHolidays(rows);
      setIsLoading(false);
    });
  }, []);

  function handleCreated(holiday) {
    setHolidays((prev) => insertSortedByDate(prev, holiday));
  }

  async function handleDelete(holidayDate) {
    setError("");
    try {
      await deleteHoliday(holidayDate);
      setHolidays((prev) => prev.filter((h) => h.holiday_date !== holidayDate));
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "刪除失敗，請稍後再試。");
    }
  }

  if (isLoading) {
    return <p className="text-sm text-text-muted">載入中…</p>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">國定假日</h2>
      <p className="text-sm text-text-muted">政府年度行事曆需每年公告，系統不自動抓取，請於年初手動維護。</p>

      <CreateHolidayForm onCreated={handleCreated} />

      {error && <p className="text-sm text-status-danger">{error}</p>}

      <div data-testid="holiday-cards" className="space-y-3 lg:hidden">
        {holidays.map((holiday) => (
          <div key={holiday.holiday_date} className="glass-panel flex items-center justify-between gap-3 rounded-xl p-4">
            <div>
              <p className="text-base font-medium text-text-primary">{holiday.holiday_date}</p>
              <p className="text-sm text-text-secondary">{holiday.name}</p>
            </div>
            <button
              type="button" onClick={() => handleDelete(holiday.holiday_date)}
              className="inline-flex min-h-11 items-center rounded-lg px-3 text-xs text-status-danger hover:underline"
            >
              刪除
            </button>
          </div>
        ))}
      </div>

      <div className="hidden glass-panel overflow-x-auto rounded-xl lg:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-text-muted">
              <th className="px-4 py-3">日期</th>
              <th className="px-4 py-3">名稱</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {holidays.map((holiday) => (
              <tr key={holiday.holiday_date} className="border-b border-border-subtle last:border-0">
                <td className="px-4 py-3 text-text-primary">{holiday.holiday_date}</td>
                <td className="px-4 py-3 text-text-primary">{holiday.name}</td>
                <td className="px-4 py-3">
                  <button
                    type="button" onClick={() => handleDelete(holiday.holiday_date)}
                    className="text-xs text-status-danger hover:underline"
                  >
                    刪除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function HolidayManagementPage() {
  return (
    <RoleGate roles={["admin"]} permissions={["holidays.manage"]}>
      <HolidayContent />
    </RoleGate>
  );
}
