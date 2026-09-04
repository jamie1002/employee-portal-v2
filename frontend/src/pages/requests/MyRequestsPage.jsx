import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMyLeaveRequests, getMyOvertimeRequests, getMyPunchRequests } from "../../api/requests.api";
import RequestStatusCell from "../../components/RequestStatusCell";
import RequestTable from "../../components/RequestTable";
import { formatDateTime } from "../../utils/datetime";

const PUNCH_TYPE_LABEL = { in: "補上班卡", out: "補下班卡", both: "補上下班卡" };

const TABS = [
  {
    key: "punch",
    label: "補打卡",
    formPath: "/requests/punch/new",
    fetcher: getMyPunchRequests,
    columns: [
      { key: "target_date", label: "日期" },
      { key: "type", label: "類型", render: (r) => PUNCH_TYPE_LABEL[r.type] ?? r.type },
      { key: "requested_in_time", label: "上班時間", render: (r) => formatDateTime(r.requested_in_time) },
      { key: "requested_out_time", label: "下班時間", render: (r) => formatDateTime(r.requested_out_time) },
      { key: "reason", label: "申請理由" },
      { key: "status", label: "狀態", render: (r) => <RequestStatusCell request={r} /> },
    ],
  },
  {
    key: "leave",
    label: "請假",
    formPath: "/requests/leave/new",
    fetcher: getMyLeaveRequests,
    columns: [
      { key: "leave_type", label: "假別" },
      { key: "start_time", label: "開始時間", render: (r) => formatDateTime(r.start_time) },
      { key: "end_time", label: "結束時間", render: (r) => formatDateTime(r.end_time) },
      { key: "hours", label: "時數" },
      { key: "status", label: "狀態", render: (r) => <RequestStatusCell request={r} /> },
    ],
  },
  {
    key: "overtime",
    label: "加班",
    formPath: "/requests/overtime/new",
    fetcher: getMyOvertimeRequests,
    columns: [
      { key: "start_time", label: "開始時間", render: (r) => formatDateTime(r.start_time) },
      { key: "end_time", label: "結束時間", render: (r) => formatDateTime(r.end_time) },
      { key: "hours", label: "時數" },
      { key: "status", label: "狀態", render: (r) => <RequestStatusCell request={r} /> },
    ],
  },
];

export default function MyRequestsPage() {
  const [activeTab, setActiveTab] = useState(TABS[0].key);
  const [status, setStatus] = useState("");
  const [records, setRecords] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  const tab = TABS.find((t) => t.key === activeTab);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    tab
      .fetcher(status ? { status } : undefined)
      .then((data) => {
        if (!cancelled) setRecords(data.requests);
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
  }, [activeTab, status, tab]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-medium text-text-primary">我的申請</h2>
        <Link
          to={tab.formPath}
          className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600"
        >
          提出{tab.label}申請
        </Link>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex gap-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setActiveTab(t.key)}
              className={`rounded-lg px-3 py-2 text-sm ${
                activeTab === t.key ? "bg-surface-700 text-accent-400" : "text-text-secondary hover:bg-surface-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary"
        >
          <option value="">全部狀態</option>
          <option value="pending">待審</option>
          <option value="approved">已核准</option>
          <option value="rejected">已駁回</option>
        </select>
      </div>

      {isLoading ? (
        <div className="glass-panel rounded-xl p-8 text-center text-text-secondary">載入中…</div>
      ) : (
        <RequestTable records={records} columns={tab.columns} />
      )}
    </div>
  );
}
