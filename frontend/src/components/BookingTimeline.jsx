import BookingBlock from "./BookingBlock";

const TIMELINE_START_HOUR = 8;
const TIMELINE_END_HOUR = 20;
const SLOT_MINUTES = 30;

const HOUR_MARKS = Array.from(
  { length: TIMELINE_END_HOUR - TIMELINE_START_HOUR + 1 },
  (_, index) => TIMELINE_START_HOUR + index,
);

// 純 CSS 百分比定位，不引入圖表函式庫（見 docs/UI-SPEC.md §4.3）。
export default function BookingTimeline({ date, rooms, bookings, currentUserId, onSlotClick, onBlockClick }) {
  const rangeStart = new Date(`${date}T${String(TIMELINE_START_HOUR).padStart(2, "0")}:00:00+08:00`);
  const rangeEnd = new Date(`${date}T${String(TIMELINE_END_HOUR).padStart(2, "0")}:00:00+08:00`);

  function handleTrackClick(event, roomId) {
    // 只在點擊軌道空白處（非色塊）時開表單；色塊自己的 onClick 已 stopPropagation。
    if (event.target !== event.currentTarget) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const totalMinutes = (TIMELINE_END_HOUR - TIMELINE_START_HOUR) * 60;
    const rawMinutes = ratio * totalMinutes;
    const snapped = Math.round(rawMinutes / SLOT_MINUTES) * SLOT_MINUTES;
    const hour = TIMELINE_START_HOUR + Math.floor(snapped / 60);
    const minute = snapped % 60;
    onSlotClick(roomId, `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`);
  }

  if (rooms.length === 0) {
    return <p className="text-sm text-text-muted">目前沒有可預約的場地。</p>;
  }

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[720px]">
        <div className="ml-32 flex border-b border-border-subtle text-xs text-text-muted">
          {HOUR_MARKS.map((hour) => (
            <div key={hour} className="flex-1 py-1 text-center">
              {String(hour).padStart(2, "0")}:00
            </div>
          ))}
        </div>

        {bookings.length === 0 && (
          <p className="py-4 text-sm text-text-muted">這一天目前沒有任何場地預約。</p>
        )}

        {rooms.map((room) => (
          <div key={room.id} className="flex items-stretch border-b border-border-subtle">
            <div className="w-32 shrink-0 py-3 pr-3 text-sm text-text-secondary">{room.name}</div>
            <div
              data-testid={`room-track-${room.id}`}
              onClick={(event) => handleTrackClick(event, room.id)}
              className="relative h-12 flex-1 cursor-pointer bg-surface-800"
            >
              {bookings
                .filter((booking) => booking.room_id === room.id)
                .map((booking) => (
                  <BookingBlock
                    key={booking.id}
                    booking={booking}
                    rangeStart={rangeStart}
                    rangeEnd={rangeEnd}
                    currentUserId={currentUserId}
                    onClick={onBlockClick}
                  />
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
