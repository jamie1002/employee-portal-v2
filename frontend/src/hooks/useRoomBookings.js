import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelRoomBooking,
  createRoomBooking,
  forceReleaseRoomBooking,
  getRoomBookings,
  getRooms,
} from "../api/rooms.api";

// 場地清單不隨日期變動，只在掛載時拉一次；預約清單則隨 date 變化重新查詢。
// `date` 在呼叫端的虛擬營業日尚未載入前會是 null——這裡先不查詢，維持載入中，
// 不要用瀏覽器的 new Date() 頂替（系統的「今天」是虛擬時鐘，見 utils/datetime.js）。
export function useRoomBookings(date) {
  const [rooms, setRooms] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const isSubmittingRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!date) return;
    const { bookings: rows } = await getRoomBookings({ date });
    setBookings(rows);
  }, [date]);

  useEffect(() => {
    getRooms().then(({ rooms: rows }) => setRooms(rows));
  }, []);

  useEffect(() => {
    if (!date) return;
    setIsLoading(true);
    refresh().finally(() => setIsLoading(false));
  }, [date, refresh]);

  async function createBooking(payload) {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    try {
      const result = await createRoomBooking(payload);
      // 成功要讓新色塊立刻帶有 room_name／booked_by_name 兩個 JOIN 欄位，
      // 失敗（多半是 409 衝突）也要 refresh，讓時間軸反映最新佔用狀況。
      await refresh();
      return result;
    } finally {
      isSubmittingRef.current = false;
    }
  }

  async function cancelBooking(bookingId) {
    await cancelRoomBooking(bookingId);
    setBookings((current) => current.filter((booking) => booking.id !== bookingId));
  }

  async function forceRelease(bookingId) {
    await forceReleaseRoomBooking(bookingId);
    setBookings((current) => current.filter((booking) => booking.id !== bookingId));
  }

  return { rooms, bookings, isLoading, createBooking, cancelBooking, forceRelease };
}
