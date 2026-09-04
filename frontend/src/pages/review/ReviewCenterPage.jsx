import { useEffect, useState } from "react";
import {
  getPendingLeaveRequests,
  getPendingOvertimeRequests,
  getPendingPunchRequests,
  reviewLeaveRequest,
  reviewOvertimeRequest,
  reviewPunchRequest,
} from "../../api/requests.api";
import RequestTable from "../../components/RequestTable";
import ReviewDialog from "../../components/ReviewDialog";
import { formatDateTime } from "../../utils/datetime";

const PUNCH_TYPE_LABEL = { in: "補上班卡", out: "補下班卡", both: "補上下班卡" };

const APPLICANT_COLUMNS = [
  { key: "applicant_name", label: "申請人" },
  { key: "department_name", label: "部門", render: (r) => r.department_name ?? "—" },
];

const TYPES = [
  {
    key: "punch",
    label: "補打卡",
    fetcher: getPendingPunchRequests,
    reviewer: reviewPunchRequest,
    columns: [
      ...APPLICANT_COLUMNS,
      { key: "target_date", label: "日期" },
      { key: "type", label: "類型", render: (r) => PUNCH_TYPE_LABEL[r.type] ?? r.type },
      { key: "reason", label: "申請理由" },
    ],
  },
  {
    key: "leave",
    label: "請假",
    fetcher: getPendingLeaveRequests,
    reviewer: reviewLeaveRequest,
    columns: [
      ...APPLICANT_COLUMNS,
      { key: "leave_type", label: "假別" },
      { key: "start_time", label: "開始時間", render: (r) => formatDateTime(r.start_time) },
      { key: "end_time", label: "結束時間", render: (r) => formatDateTime(r.end_time) },
      { key: "hours", label: "時數" },
    ],
  },
  {
    key: "overtime",
    label: "加班",
    fetcher: getPendingOvertimeRequests,
    reviewer: reviewOvertimeRequest,
    columns: [
      ...APPLICANT_COLUMNS,
      { key: "start_time", label: "開始時間", render: (r) => formatDateTime(r.start_time) },
      { key: "end_time", label: "結束時間", render: (r) => formatDateTime(r.end_time) },
      { key: "hours", label: "時數" },
    ],
  },
];

export default function ReviewCenterPage() {
  const [activeTab, setActiveTab] = useState(TYPES[0].key);
  const [listByType, setListByType] = useState({ punch: [], leave: [], overtime: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [submittingId, setSubmittingId] = useState(null);

  async function loadTab(key) {
    const type = TYPES.find((t) => t.key === key);
    const data = await type.fetcher();
    setListByType((prev) => ({ ...prev, [key]: data.requests }));
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all(TYPES.map((t) => t.fetcher().then((data) => [t.key, data.requests])))
      .then((entries) => {
        if (cancelled) return;
        setListByType(Object.fromEntries(entries));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const type = TYPES.find((t) => t.key === activeTab);
  const records = listByType[activeTab] ?? [];

  async function handleReview(id, payload) {
    setSubmittingId(id);
    setToast("");
    try {
      await type.reviewer(id, payload);
      setListByType((prev) => ({
        ...prev,
        [activeTab]: prev[activeTab].filter((record) => record.id !== id),
      }));
    } catch (err) {
      if (err.response?.status === 409) {
        setToast("此申請已被其他人審核，清單已重新載入。");
        await loadTab(activeTab);
      } else {
        setToast(err.response?.data?.error?.message ?? "審核失敗，請稍後再試。");
      }
    } finally {
      setSubmittingId(null);
    }
  }

  const columns = [
    ...type.columns,
    {
      key: "actions",
      label: "審核",
      render: (record) => (
        <ReviewDialog
          isSubmitting={submittingId === record.id}
          onApprove={() => handleReview(record.id, { action: "approve" })}
          onReject={(note) => handleReview(record.id, { action: "reject", review_note: note })}
        />
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">審核中心</h2>

      {toast && <div className="glass-panel rounded-xl p-3 text-sm text-status-danger">{toast}</div>}

      <div className="flex gap-2">
        {TYPES.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActiveTab(t.key)}
            className={`rounded-lg px-3 py-2 text-sm ${
              activeTab === t.key ? "bg-surface-700 text-accent-400" : "text-text-secondary hover:bg-surface-800"
            }`}
          >
            {t.label}（{(listByType[t.key] ?? []).length}）
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="glass-panel rounded-xl p-8 text-center text-text-secondary">載入中…</div>
      ) : (
        <RequestTable records={records} columns={columns} emptyMessage="目前沒有待審申請。" />
      )}
    </div>
  );
}
