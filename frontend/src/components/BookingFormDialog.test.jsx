import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import BookingFormDialog from "./BookingFormDialog";

const ROOMS = [
  { id: 1, name: "會議室 A" },
  { id: 2, name: "會議室 B" },
];

function fillAndSubmit({ startTime = "09:00", endTime = "10:00", title = "部門會議" } = {}) {
  fireEvent.change(screen.getByLabelText("預約標題"), { target: { value: title } });
  fireEvent.change(screen.getByLabelText("開始時間"), { target: { value: startTime } });
  fireEvent.change(screen.getByLabelText("結束時間"), { target: { value: endTime } });
  fireEvent.click(screen.getByRole("button", { name: "確認預約" }));
}

test("欄位齊全時以正確格式組出 payload 呼叫 onSubmit", () => {
  const onSubmit = vi.fn();
  render(
    <BookingFormDialog date="2026-08-24" rooms={ROOMS} isSubmitting={false} errorMessage="" onSubmit={onSubmit} onClose={vi.fn()} />,
  );

  fillAndSubmit();

  expect(onSubmit).toHaveBeenCalledWith({
    room_id: 1,
    title: "部門會議",
    start_time: "2026-08-24T09:00:00+08:00",
    end_time: "2026-08-24T10:00:00+08:00",
  });
});

test("結束時間早於開始時間時前端擋下，不呼叫 onSubmit", () => {
  const onSubmit = vi.fn();
  render(
    <BookingFormDialog date="2026-08-24" rooms={ROOMS} isSubmitting={false} errorMessage="" onSubmit={onSubmit} onClose={vi.fn()} />,
  );

  fillAndSubmit({ startTime: "10:00", endTime: "09:00" });

  expect(onSubmit).not.toHaveBeenCalled();
  expect(screen.getByText("結束時間必須晚於開始時間。")).toBeInTheDocument();
});

test("initialRoomId／initialStartTime 會預填對應欄位", () => {
  render(
    <BookingFormDialog
      date="2026-08-24"
      rooms={ROOMS}
      initialRoomId={2}
      initialStartTime="14:00"
      isSubmitting={false}
      errorMessage=""
      onSubmit={vi.fn()}
      onClose={vi.fn()}
    />,
  );

  expect(screen.getByLabelText("場地")).toHaveValue("2");
  expect(screen.getByLabelText("開始時間")).toHaveValue("14:00");
});

test("點擊取消會呼叫 onClose", () => {
  const onClose = vi.fn();
  render(
    <BookingFormDialog date="2026-08-24" rooms={ROOMS} isSubmitting={false} errorMessage="" onSubmit={vi.fn()} onClose={onClose} />,
  );

  fireEvent.click(screen.getByRole("button", { name: "取消" }));

  expect(onClose).toHaveBeenCalled();
});
