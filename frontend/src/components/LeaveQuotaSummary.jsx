import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMyLeaveQuota } from "../api/leaveQuota.api";

export default function LeaveQuotaSummary() {
  const [quotas, setQuotas] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getMyLeaveQuota()
      .then((data) => {
        if (!cancelled) setQuotas(data.quota);
      })
      .catch(() => {
        if (!cancelled) setQuotas([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!quotas) {
    return <div className="glass-panel rounded-xl p-6 text-text-secondary">載入中…</div>;
  }

  return (
    <div className="glass-panel rounded-xl p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-text-primary">假別剩餘量</h3>
        <Link to="/leave-balance" className="text-sm text-accent-400 hover:underline">
          查看詳情
        </Link>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* 公假不設剩餘量概念，整列不顯示，而非只隱藏數字（見 SPEC.md §4.3.1）。 */}
        {quotas
          .filter((quota) => quota.leave_type !== "公假")
          .map((quota) => (
            <div key={quota.leave_type} className="rounded-lg border border-border-subtle p-3">
              <p className="text-xs text-text-muted">{quota.leave_type}</p>
              <p className="mt-1 text-lg font-medium text-accent-400">
                {quota.remaining_hours ?? "不限"}
                {quota.remaining_hours !== null && <span className="ml-1 text-xs text-text-muted">小時</span>}
              </p>
            </div>
          ))}
      </div>
    </div>
  );
}
