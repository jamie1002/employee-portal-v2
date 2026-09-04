import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import VenueBookingPage from "./VenueBookingPage";

const mockGetRooms = vi.fn();
const mockGetBookings = vi.fn();
const mockCreate = vi.fn();
const mockCancel = vi.fn();
const mockForceRelease = vi.fn();
vi.mock("../api/rooms.api", () => ({
  getRooms: (...args) => mockGetRooms(...args),
  getRoomBookings: (...args) => mockGetBookings(...args),
  createRoomBooking: (...args) => mockCreate(...args),
  cancelRoomBooking: (...args) => mockCancel(...args),
  forceReleaseRoomBooking: (...args) => mockForceRelease(...args),
}));

// 預設日期取自虛擬時鐘的營業日（today.punch_date），走 useAttendance 既有的
// getToday()，不是瀏覽器的 new Date()——mock 掉這支才能讓頁面知道「今天」是哪一天。
vi.mock("../api/attendance.api", () => ({
  getToday: () => Promise.resolve({ attendance: { punch_date: "2026-08-24" } }),
}));

let mockUser = { id: 3, name: "陳小華", role: "employee" };
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

const ROOMS = [{ id: 1, name: "會議室 A", capacity: 8, location_info: "3F" }];
const BOOKING = {
  id: 10, room_id: 1, user_id: 3, title: "既有預約",
  start_time: "2026-08-24T01:00:00+08:00", end_time: "2026-08-24T03:00:00+08:00",
  status: "confirmed", room_name: "會議室 A", booked_by_name: "陳小華",
};

beforeEach(() => {
  mockUser = { id: 3, name: "陳小華", role: "employee" };
  mockGetRooms.mockReset().mockResolvedValue({ rooms: ROOMS });
  mockGetBookings.mockReset().mockResolvedValue({ bookings: [BOOKING] });
  mockCreate.mockReset();
  mockCancel.mockReset();
  mockForceRelease.mockReset();
});

test("載入後顯示時間軸上的既有預約", async () => {
  render(<VenueBookingPage />);

  await waitFor(() => expect(screen.getByRole("button", { name: /既有預約/ })).toBeInTheDocument());
});

test("點擊本人的預約色塊可以取消", async () => {
  mockCancel.mockResolvedValue({});
  render(<VenueBookingPage />);
  await waitFor(() => screen.getByRole("button", { name: /既有預約/ }));

  fireEvent.click(screen.getByRole("button", { name: /既有預約/ }));
  await waitFor(() => expect(screen.getByRole("button", { name: "取消預約" })).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "強制釋放" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "取消預約" }));

  await waitFor(() => expect(mockCancel).toHaveBeenCalledWith(10));
});

test("admin 看到他人的預約時只顯示強制釋放，不顯示取消預約", async () => {
  mockUser = { id: 99, name: "系統管理者", role: "admin" };
  mockForceRelease.mockResolvedValue({});
  render(<VenueBookingPage />);
  await waitFor(() => screen.getByRole("button", { name: /既有預約/ }));

  fireEvent.click(screen.getByRole("button", { name: /既有預約/ }));

  await waitFor(() => expect(screen.getByRole("button", { name: "強制釋放" })).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "取消預約" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "強制釋放" }));
  await waitFor(() => expect(mockForceRelease).toHaveBeenCalledWith(10));
});

test("新增預約表單送出成功後關閉表單並重新整理清單", async () => {
  mockCreate.mockResolvedValue({ booking: { id: 20 } });
  render(<VenueBookingPage />);
  await waitFor(() => screen.getByRole("button", { name: /既有預約/ }));

  fireEvent.click(screen.getByRole("button", { name: "新增預約" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "新增預約" })).toBeInTheDocument());

  fireEvent.change(screen.getByLabelText("預約標題"), { target: { value: "新會議" } });
  fireEvent.change(screen.getByLabelText("開始時間"), { target: { value: "14:00" } });
  fireEvent.change(screen.getByLabelText("結束時間"), { target: { value: "15:00" } });
  fireEvent.click(screen.getByRole("button", { name: "確認預約" }));

  await waitFor(() => expect(mockCreate).toHaveBeenCalled());
  await waitFor(() => expect(screen.queryByRole("heading", { name: "新增預約" })).not.toBeInTheDocument());
});
