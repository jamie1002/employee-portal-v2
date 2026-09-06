import { useSyncExternalStore } from "react";
import { getSlowRequestCount, subscribeSlowRequests } from "../api/client";

// Render 免費方案長時間無人使用後，第一次請求會有數十秒的冷啟動延遲
// （見 docs/PITFALLS.md G5）。請求超過 3 秒才顯示，避免正常請求也閃一下；
// 用集合而非布林值追蹤，多個並行慢請求只顯示一個橫幅，且要全部完成才收起。
export default function ColdStartBanner() {
  const slowRequestCount = useSyncExternalStore(subscribeSlowRequests, getSlowRequestCount, () => 0);

  if (slowRequestCount === 0) return null;

  return (
    <div role="status" className="fixed inset-x-0 top-0 z-50 bg-accent-600 text-surface-950">
      <div className="mx-auto flex max-w-3xl items-center justify-center gap-3 px-4 py-2 text-sm font-medium">
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-surface-950 border-t-transparent" />
        系統正在喚醒雲端伺服器（預計需 20~30 秒），請稍候...
      </div>
    </div>
  );
}
