import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import BookingBlock from "./BookingBlock";

const RANGE_START = new Date("2026-08-24T00:00:00+08:00");
const RANGE_END = new Date("2026-08-24T12:00:00+08:00");

const BOOKING = {
  id: 1,
  title: "部門會議",
  user_id: 3,
  start_time: "2026-08-24T01:00:00+08:00", // 台北 09:00，落在區間 1/12 起
  end_time: "2026-08-24T03:00:00+08:00", // 台北 11:00
  booked_by_name: "陳小華",
};

test("非本人的預約套用一般色", () => {
  const onClick = vi.fn();
  render(
    <BookingBlock booking={BOOKING} rangeStart={RANGE_START} rangeEnd={RANGE_END} currentUserId={99} onClick={onClick} />,
  );

  const block = screen.getByRole("button", { name: /部門會議/ });
  expect(block.className).toContain("bg-status-normal");
  expect(block.className).not.toContain("ring-2");
});

test("本人的預約套用強調色與外框，且點擊會呼叫 onClick 並阻止冒泡", () => {
  const onClick = vi.fn();
  render(
    <BookingBlock booking={BOOKING} rangeStart={RANGE_START} rangeEnd={RANGE_END} currentUserId={3} onClick={onClick} />,
  );

  const block = screen.getByRole("button", { name: /部門會議/ });
  expect(block.className).toContain("ring-2");

  fireEvent.click(block);
  expect(onClick).toHaveBeenCalledWith(BOOKING);
});
