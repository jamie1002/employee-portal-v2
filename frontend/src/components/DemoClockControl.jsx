import { useEffect, useState } from "react";
import { setDemoClock } from "../api/demo.api";
import { useVirtualClock } from "../hooks/useVirtualClock";

const MIN_DATETIME = "2026-08-24T00:00";
const MAX_DATETIME = "2026-08-31T23:59";
const TAIPEI_OFFSET = "+08:00";

function formatDisplay(date) {
  if (!date) return "—";
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  }).format(date);
}

// <input type="datetime-local"> 沒有 value 時，瀏覽器的日期選擇器預設帶入真實的
// 現在時間；虛擬時鐘的合法範圍卡在 2026-08-24 ~ 08-31，真實現在必然落在範圍外，
// 選擇器就會夾到 max（08-31）——使用者看到的「每次都跳到 8 月 31 日」就是這個瀏覽
// 器行為，不是我們的程式碼真的用了現在時間。用展示時間本身當預設值即可避免。
function toDatetimeLocalValue(date) {
  if (!date) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date);
  const get = (type) => parts.find((part) => part.type === type)?.value;
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

export default function DemoClockControl() {
  const virtualNow = useVirtualClock();
  const [draft, setDraft] = useState("");
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState("");

  // 只在欄位還沒被使用者動過（draft 是空字串）時，用展示時間補一次預設值；
  // 使用者開始選別的時間之後就不再覆蓋，避免手動選好的值被下一次 tick 蓋掉。
  useEffect(() => {
    if (virtualNow && !draft) {
      setDraft(toDatetimeLocalValue(virtualNow));
    }
  }, [virtualNow, draft]);

  async function handleApply() {
    if (!draft) return;
    setIsApplying(true);
    setError("");
    try {
      await setDemoClock(`${draft}:00${TAIPEI_OFFSET}`);
      // 套用新時間後整頁重新載入：畫面上大多數元件只在掛載時抓資料，
      // 局部更新沒辦法反映「現在是另一天」帶來的一連串連鎖狀態變化。
      window.location.reload();
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "調整失敗，請稍後再試。");
      setIsApplying(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
      <span>展示時間：{formatDisplay(virtualNow)}</span>
      <input
        type="datetime-local"
        aria-label="調整展示時間"
        min={MIN_DATETIME}
        max={MAX_DATETIME}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        className="rounded-lg border border-border-subtle bg-surface-900 px-2 py-1 text-xs text-text-primary focus:border-accent-500 focus:outline-none"
      />
      <button
        type="button"
        disabled={!draft || isApplying}
        onClick={handleApply}
        className="rounded-lg border border-accent-500 px-2 py-1 text-xs text-accent-400 hover:bg-surface-800 disabled:opacity-50"
      >
        {isApplying ? "套用中…" : "套用"}
      </button>
      {error && <span className="text-xs text-status-danger">{error}</span>}
    </div>
  );
}
