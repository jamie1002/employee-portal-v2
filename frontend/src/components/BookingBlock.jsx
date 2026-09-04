import { formatTime } from "../utils/datetime";

// 位置一律用 epoch ms 相減計算，不經過本地時區轉換——時間軸的視覺定位只在乎
// 「這個時間點落在整段區間的百分之幾」，跟顯示用哪個時區無關（見 docs/UI-SPEC.md §4.3）。
export default function BookingBlock({ booking, rangeStart, rangeEnd, currentUserId, onClick }) {
  const start = new Date(booking.start_time);
  const end = new Date(booking.end_time);
  const totalMs = rangeEnd.getTime() - rangeStart.getTime();
  const left = ((start.getTime() - rangeStart.getTime()) / totalMs) * 100;
  const width = ((end.getTime() - start.getTime()) / totalMs) * 100;
  const isMine = booking.user_id === currentUserId;

  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onClick(booking);
      }}
      style={{ left: `${left}%`, width: `${width}%` }}
      className={`absolute top-1 bottom-1 overflow-hidden rounded-md px-2 text-left text-xs font-medium ${
        isMine ? "bg-accent-400 text-surface-950 ring-2 ring-accent-600" : "bg-status-normal text-surface-950"
      }`}
      title={`${booking.title}（${formatTime(booking.start_time)}–${formatTime(booking.end_time)}，${booking.booked_by_name}）`}
    >
      <span className="block truncate">{booking.title}</span>
    </button>
  );
}
