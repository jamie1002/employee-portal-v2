import { useState } from "react";

const inputClass =
  "rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

// 日期由外部 date prop 鎖定（同一天內選時間），故「不得跨日」在此表單結構下天然成立。
export default function BookingFormDialog({
  date,
  rooms,
  initialRoomId,
  initialStartTime,
  isSubmitting,
  errorMessage,
  onSubmit,
  onClose,
}) {
  const [roomId, setRoomId] = useState(initialRoomId ?? rooms[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [startTime, setStartTime] = useState(initialStartTime ?? "");
  const [endTime, setEndTime] = useState("");
  const [localError, setLocalError] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    if (!roomId || !title.trim() || !startTime || !endTime) {
      setLocalError("請完整填寫所有欄位。");
      return;
    }
    if (endTime <= startTime) {
      setLocalError("結束時間必須晚於開始時間。");
      return;
    }
    setLocalError("");
    onSubmit({
      room_id: Number(roomId),
      title: title.trim(),
      start_time: `${date}T${startTime}:00+08:00`,
      end_time: `${date}T${endTime}:00+08:00`,
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/60 sm:items-center sm:p-4">
      <form
        onSubmit={handleSubmit}
        className="glass-panel h-full w-full space-y-4 overflow-y-auto rounded-none p-6 sm:h-auto sm:max-w-md sm:rounded-xl"
      >
        <h3 className="text-lg font-medium text-text-primary">新增預約</h3>

        {(localError || errorMessage) && (
          <p className="text-sm text-status-danger">{localError || errorMessage}</p>
        )}

        <div>
          <label htmlFor="booking-room" className="mb-1 block text-xs text-text-muted">
            場地
          </label>
          <select
            id="booking-room"
            value={roomId}
            onChange={(event) => setRoomId(event.target.value)}
            className={`w-full ${inputClass}`}
          >
            {rooms.map((room) => (
              <option key={room.id} value={room.id}>
                {room.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="booking-title" className="mb-1 block text-xs text-text-muted">
            預約標題
          </label>
          <input
            id="booking-title"
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className={`w-full ${inputClass}`}
          />
        </div>

        <div className="flex gap-4">
          <div className="flex-1">
            <label htmlFor="booking-start-time" className="mb-1 block text-xs text-text-muted">
              開始時間
            </label>
            <input
              id="booking-start-time"
              type="time"
              value={startTime}
              onChange={(event) => setStartTime(event.target.value)}
              className={`w-full ${inputClass}`}
            />
          </div>
          <div className="flex-1">
            <label htmlFor="booking-end-time" className="mb-1 block text-xs text-text-muted">
              結束時間
            </label>
            <input
              id="booking-end-time"
              type="time"
              value={endTime}
              onChange={(event) => setEndTime(event.target.value)}
              className={`w-full ${inputClass}`}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border-subtle px-4 py-2 text-sm text-text-secondary hover:text-text-primary"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
          >
            {isSubmitting ? "送出中…" : "確認預約"}
          </button>
        </div>
      </form>
    </div>
  );
}
