import { useEffect, useState } from "react";
import { getMyLeaveQuota } from "../api/leaveQuota.api";

function barColor(usedRatio) {
  if (usedRatio >= 0.9) return "bg-status-danger";
  if (usedRatio >= 0.7) return "bg-status-late";
  return "bg-accent-500";
}

function QuotaCard({ quota }) {
  const { leave_type: leaveType, quota_hours: quotaHours, used_hours: usedHours, remaining_hours: remainingHours } = quota;
  const unlimited = quotaHours === null;
  const ratio = unlimited || quotaHours === 0 ? 0 : Math.min(usedHours / quotaHours, 1);

  return (
    <div className="glass-panel rounded-xl p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-lg font-medium text-text-primary">{leaveType}</h3>
        <span className="text-xs text-text-muted">
          {quota.period_start} ~ {quota.period_end}
        </span>
      </div>

      {unlimited ? (
        <p className="mt-3 text-sm text-text-secondary">不設固定上限，已使用 {usedHours} 小時。</p>
      ) : (
        <>
          <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-surface-800">
            <div className={`h-full rounded-full ${barColor(ratio)}`} style={{ width: `${Math.round(ratio * 100)}%` }} />
          </div>
          <p className="mt-2 text-sm text-text-secondary">
            已用 <span className="font-medium text-text-primary">{usedHours}</span> / {quotaHours} 小時，
            剩餘 <span className="font-medium text-accent-400">{remainingHours}</span> 小時
          </p>
        </>
      )}
    </div>
  );
}

export default function LeaveBalancePage() {
  const [quotas, setQuotas] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getMyLeaveQuota()
      .then((data) => {
        if (!cancelled) setQuotas(data.quota);
      })
      .catch(() => {
        if (!cancelled) setQuotas([]);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading) {
    return <div className="glass-panel rounded-xl p-8 text-center text-text-secondary">載入中…</div>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">假別剩餘量</h2>
      <p className="text-sm text-text-secondary">
        特別休假依到職週年制計算，事假／病假／公假依曆年制（每年 1/1 歸零）計算。
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        {quotas.map((quota) => (
          <QuotaCard key={quota.leave_type} quota={quota} />
        ))}
      </div>
    </div>
  );
}
