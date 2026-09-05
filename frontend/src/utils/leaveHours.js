// 請假時數的前端本地預覽（UI-SPEC.md §3.8「即時預估時數」）。
//
// 演算法必須跟後端 backend/app/services/leave_hours.py 的 calculate_leave_hours_by_day()
// 逐步對應：逐工作日切分、排除週末與國定假日、緩衝只套用在整段請假區間真正的
// 頭尾兩端、午休固定不浮動。這裡只是預覽，正式時數以送出後的後端回應為準，但
// 演算法本身不能各算一套，否則預覽數字會誤導使用者。

const TAIPEI_OFFSET = "+08:00";

function combine(dateStr, timeStr) {
  // timeStr 可能是 "HH:mm" 或後端設定值的 "HH:mm:ss"，統一只取到分鐘。
  const [hour, minute] = timeStr.split(":");
  return new Date(`${dateStr}T${hour}:${minute}:00${TAIPEI_OFFSET}`);
}

function addMinutes(date, minutes) {
  return new Date(date.getTime() + minutes * 60_000);
}

// 用 Date.UTC 而非瀏覽器本地時區建構，星期幾是曆法日期本身的性質、跟時區無關，
// 避免瀏覽器所在時區在日期邊界附近算錯。
function dayOfWeek(dateStr) {
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).getUTCDay(); // 0=Sun ... 6=Sat
}

function nextDateString(dateStr) {
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
}

/**
 * @param {object} params
 * @param {string} params.startDate 'YYYY-MM-DD'
 * @param {string} params.startTime 'HH:mm'
 * @param {string} params.endDate 'YYYY-MM-DD'
 * @param {string} params.endTime 'HH:mm'
 * @param {{work_start_time:string, work_end_time:string, lunch_start_time:string, lunch_end_time:string, grace_period_minutes:number}} params.settings
 * @param {Set<string>} [params.holidayDates] 'YYYY-MM-DD' 集合
 * @returns {number} 預估時數，四捨五入至小數點後兩位；輸入不完整或區間無效時回傳 0
 */
export function estimateLeaveHours({ startDate, startTime, endDate, endTime, settings, holidayDates }) {
  if (!startDate || !startTime || !endDate || !endTime || !settings || endDate < startDate) return 0;

  const start = combine(startDate, startTime);
  const end = combine(endDate, endTime);
  if (!(end > start)) return 0;

  const grace = settings.grace_period_minutes ?? 0;
  const holidays = holidayDates ?? new Set();

  let totalMs = 0;
  let cursor = startDate;
  while (cursor <= endDate) {
    const dow = dayOfWeek(cursor);
    if (dow !== 0 && dow !== 6 && !holidays.has(cursor)) {
      const startGrace = cursor === startDate ? grace : 0;
      const endGrace = cursor === endDate ? grace : 0;

      const dayWorkStart = addMinutes(combine(cursor, settings.work_start_time), -startGrace);
      const dayWorkEnd = addMinutes(combine(cursor, settings.work_end_time), endGrace);
      const dayLunchStart = combine(cursor, settings.lunch_start_time);
      const dayLunchEnd = combine(cursor, settings.lunch_end_time);

      for (const [segmentStart, segmentEnd] of [
        [dayWorkStart, dayLunchStart],
        [dayLunchEnd, dayWorkEnd],
      ]) {
        const lo = start > segmentStart ? start : segmentStart;
        const hi = end < segmentEnd ? end : segmentEnd;
        if (hi > lo) totalMs += hi.getTime() - lo.getTime();
      }
    }
    cursor = nextDateString(cursor);
  }

  return Math.round((totalMs / 3_600_000) * 100) / 100;
}
