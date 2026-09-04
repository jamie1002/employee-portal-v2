// 集中的日期時間格式化：全站共用同一份定義，避免各頁面各自實作出格式不一致的版本。
// 一律以台北時區呈現（後端存 UTC、算用台北、顯示用台北）。

const TIMEZONE = "Asia/Taipei";

export function formatTime(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleTimeString("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: TIMEZONE,
  });
}

export function formatDateTime(isoString, { withYear = false } = {}) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleString("zh-TW", {
    ...(withYear ? { year: "numeric" } : {}),
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: TIMEZONE,
  });
}

// 授權紀錄的「由 X 於 M/D 授予」只需要月/日，不需要完整日期時間。
export function formatMonthDay(isoString) {
  if (!isoString) return "—";
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: TIMEZONE, month: "numeric", day: "numeric" }).formatToParts(
    new Date(isoString),
  );
  const month = parts.find((p) => p.type === "month").value;
  const day = parts.find((p) => p.type === "day").value;
  return `${month}/${day}`;
}

export function taipeiDateKey(isoString) {
  return new Date(isoString).toLocaleDateString("en-CA", { timeZone: TIMEZONE });
}

// 由「後端回傳的營業日字串」算出當月起訖，刻意不用 new Date() 取瀏覽器的今天
// ——系統的「今天」是展示用虛擬時鐘，與瀏覽器的真實日期無關。
export function monthRangeOf(dateString) {
  const [year, month] = dateString.split("-").map(Number);
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const pad = (value) => String(value).padStart(2, "0");
  return {
    startDate: `${year}-${pad(month)}-01`,
    endDate: `${year}-${pad(month)}-${pad(lastDay)}`,
  };
}
