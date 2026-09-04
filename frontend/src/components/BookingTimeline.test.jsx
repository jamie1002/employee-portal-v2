import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import BookingTimeline from "./BookingTimeline";

const ROOMS = [
  { id: 1, name: "會議室 A" },
  { id: 2, name: "會議室 B" },
];

const BOOKINGS = [
  {
    id: 10, room_id: 1, user_id: 3, title: "既有預約",
    start_time: "2026-08-24T01:00:00+08:00", end_time: "2026-08-24T03:00:00+08:00",
    booked_by_name: "陳小華",
  },
];

test("沒有任何預約時顯示空狀態文案", () => {
  render(
    <BookingTimeline date="2026-08-24" rooms={ROOMS} bookings={[]} currentUserId={3} onSlotClick={vi.fn()} onBlockClick={vi.fn()} />,
  );

  expect(screen.getByText("這一天目前沒有任何場地預約。")).toBeInTheDocument();
});

test("沒有可預約場地時顯示對應提示", () => {
  render(
    <BookingTimeline date="2026-08-24" rooms={[]} bookings={[]} currentUserId={3} onSlotClick={vi.fn()} onBlockClick={vi.fn()} />,
  );

  expect(screen.getByText("目前沒有可預約的場地。")).toBeInTheDocument();
});

test("點擊軌道空白處會以場地與時間呼叫 onSlotClick", () => {
  const onSlotClick = vi.fn();
  render(
    <BookingTimeline date="2026-08-24" rooms={ROOMS} bookings={BOOKINGS} currentUserId={3} onSlotClick={onSlotClick} onBlockClick={vi.fn()} />,
  );

  const track = screen.getByTestId("room-track-2");
  vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0, width: 240 });
  fireEvent.click(track, { clientX: 0 });

  expect(onSlotClick).toHaveBeenCalledWith(2, "08:00");
});

test("點擊色塊會呼叫 onBlockClick 而不是 onSlotClick", () => {
  const onSlotClick = vi.fn();
  const onBlockClick = vi.fn();
  render(
    <BookingTimeline date="2026-08-24" rooms={ROOMS} bookings={BOOKINGS} currentUserId={3} onSlotClick={onSlotClick} onBlockClick={onBlockClick} />,
  );

  fireEvent.click(screen.getByRole("button", { name: /既有預約/ }));

  expect(onBlockClick).toHaveBeenCalledWith(BOOKINGS[0]);
  expect(onSlotClick).not.toHaveBeenCalled();
});
