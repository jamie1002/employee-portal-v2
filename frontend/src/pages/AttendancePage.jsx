import { useEffect, useState } from "react";
import { getMyRecords } from "../api/attendance.api";
import AttendanceTable from "../components/AttendanceTable";
import DatePickerField from "../components/DatePickerField";
import { useVirtualToday } from "../hooks/useVirtualClock";

const PAGE_SIZE = 10;

// 狀態篩選比對的是**生效值**；early_leave 與 missing_punch_out 是讀取時才衍生的
// 判定，不是 status 欄位本身的列舉值（見後端 services/attendance_effective.py）。
const STATUS_OPTIONS = [
  { value: "", label: "全部狀態" },
  { value: "normal", label: "正常" },
  { value: "late", label: "遲到" },
  { value: "absent", label: "缺勤" },
  { value: "holiday_work", label: "假日出勤" },
  { value: "on_leave", label: "請假" },
  { value: "early_leave", label: "早退" },
  { value: "missing_punch_out", label: "未打下班卡" },
];

export default function AttendancePage() {
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [status, setStatus] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  // 欄位本身維持空白（不限日期、顯示全部），只有日曆彈出視窗的初始瀏覽月份
  // 用展示用虛擬時鐘的今天，不用真實現在時間（見 docs/PITFALLS.md B7）。
  const virtualToday = useVirtualToday();

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    getMyRecords({
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      status: status || undefined,
      page,
      page_size: PAGE_SIZE,
    })
      .then((data) => {
        if (cancelled) return;
        setRecords(data.records);
        setTotal(data.total);
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
  }, [startDate, endDate, status, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const inputClass =
    "w-full sm:w-auto rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">出勤紀錄</h2>

      <div className="glass-panel flex flex-wrap items-end gap-4 rounded-xl p-4">
        <DatePickerField
          id="start-date"
          label="起始日期"
          value={startDate}
          initialViewDate={virtualToday}
          onChange={(value) => {
            setPage(1);
            setStartDate(value);
          }}
        />
        <DatePickerField
          id="end-date"
          label="結束日期"
          value={endDate}
          initialViewDate={virtualToday}
          onChange={(value) => {
            setPage(1);
            setEndDate(value);
          }}
        />
        <div>
          <label htmlFor="status" className="mb-1 block text-xs text-text-muted">
            狀態
          </label>
          <select
            id="status"
            value={status}
            onChange={(event) => {
              setPage(1);
              setStatus(event.target.value);
            }}
            className={inputClass}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="glass-panel rounded-xl p-8 text-center text-text-secondary">載入中…</div>
      ) : (
        <AttendanceTable records={records} />
      )}

      <div className="flex items-center justify-between text-sm text-text-secondary">
        <span>共 {total} 筆</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((current) => current - 1)}
            className="rounded-lg border border-border-subtle px-3 py-1 disabled:opacity-50"
          >
            上一頁
          </button>
          <span>
            {page} / {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((current) => current + 1)}
            className="rounded-lg border border-border-subtle px-3 py-1 disabled:opacity-50"
          >
            下一頁
          </button>
        </div>
      </div>
    </div>
  );
}
