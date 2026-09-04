import { useState } from "react";
import BookingFormDialog from "../components/BookingFormDialog";
import BookingTimeline from "../components/BookingTimeline";
import { useAuth } from "../context/AuthContext";
import { useAttendance } from "../hooks/useAttendance";
import { useRoomBookings } from "../hooks/useRoomBookings";
import { formatTime } from "../utils/datetime";

const inputClass =
  "rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

export default function VenueBookingPage() {
  const { user } = useAuth();
  // 預設日期取自虛擬時鐘的營業日（今日出勤狀態的 punch_date），不用 new Date()
  // 取瀏覽器的今天——系統的「今天」是虛擬時鐘，與 MonthlyAttendanceSummary 同一套慣例。
  const { today } = useAttendance();
  const [dateOverride, setDateOverride] = useState(null);
  const date = dateOverride ?? today?.punch_date ?? null;
  const { rooms, bookings, isLoading, createBooking, cancelBooking, forceRelease } = useRoomBookings(date);

  const [formState, setFormState] = useState(null); // { roomId, startTime } | null
  const [formError, setFormError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [actionError, setActionError] = useState("");

  function openFormForSlot(roomId, startTime) {
    setFormError("");
    setFormState({ roomId, startTime });
  }

  async function handleCreate(payload) {
    setIsSubmitting(true);
    setFormError("");
    try {
      await createBooking(payload);
      setFormState(null);
    } catch (err) {
      setFormError(err.response?.data?.error?.message ?? "預約失敗，請稍後再試。");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCancel(bookingId) {
    setActionError("");
    try {
      await cancelBooking(bookingId);
      setSelectedBooking(null);
    } catch (err) {
      setActionError(err.response?.data?.error?.message ?? "取消失敗，請稍後再試。");
    }
  }

  async function handleForceRelease(bookingId) {
    setActionError("");
    try {
      await forceRelease(bookingId);
      setSelectedBooking(null);
    } catch (err) {
      setActionError(err.response?.data?.error?.message ?? "強制釋放失敗，請稍後再試。");
    }
  }

  const isMine = selectedBooking?.user_id === user.id;
  const isAdmin = user.role === "admin";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-medium text-text-primary">場地借用</h2>
        <div className="flex items-center gap-3">
          <label htmlFor="venue-date" className="text-xs text-text-muted">
            日期
          </label>
          <input
            id="venue-date"
            type="date"
            value={date ?? ""}
            onChange={(event) => setDateOverride(event.target.value)}
            className={inputClass}
          />
          <button
            type="button"
            onClick={() => openFormForSlot(rooms[0]?.id, "")}
            disabled={rooms.length === 0 || !date}
            className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
          >
            新增預約
          </button>
        </div>
      </div>

      <div className="glass-panel rounded-xl p-4">
        {isLoading ? (
          <p className="text-sm text-text-muted">載入中…</p>
        ) : (
          <BookingTimeline
            date={date}
            rooms={rooms}
            bookings={bookings}
            currentUserId={user.id}
            onSlotClick={openFormForSlot}
            onBlockClick={setSelectedBooking}
          />
        )}
      </div>

      {formState && (
        <BookingFormDialog
          date={date}
          rooms={rooms}
          initialRoomId={formState.roomId}
          initialStartTime={formState.startTime}
          isSubmitting={isSubmitting}
          errorMessage={formError}
          onSubmit={handleCreate}
          onClose={() => setFormState(null)}
        />
      )}

      {selectedBooking && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="glass-panel w-full max-w-md space-y-3 rounded-xl p-6">
            <h3 className="text-lg font-medium text-text-primary">{selectedBooking.title}</h3>
            <p className="text-sm text-text-secondary">{selectedBooking.room_name}</p>
            <p className="text-sm text-text-secondary">
              {formatTime(selectedBooking.start_time)}–{formatTime(selectedBooking.end_time)}
            </p>
            <p className="text-sm text-text-secondary">預約人：{selectedBooking.booked_by_name}</p>

            {actionError && <p className="text-sm text-status-danger">{actionError}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setSelectedBooking(null)}
                className="rounded-lg border border-border-subtle px-4 py-2 text-sm text-text-secondary hover:text-text-primary"
              >
                關閉
              </button>
              {isMine && (
                <button
                  type="button"
                  onClick={() => handleCancel(selectedBooking.id)}
                  className="rounded-lg border border-status-danger px-4 py-2 text-sm text-status-danger hover:bg-status-danger/10"
                >
                  取消預約
                </button>
              )}
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => handleForceRelease(selectedBooking.id)}
                  className="rounded-lg bg-status-danger px-4 py-2 text-sm font-medium text-surface-950 hover:opacity-90"
                >
                  強制釋放
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
