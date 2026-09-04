import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import ReviewDialog from "./ReviewDialog";

test("核准直接呼叫 onApprove，不需要額外表單", () => {
  const onApprove = vi.fn();
  render(<ReviewDialog onApprove={onApprove} onReject={vi.fn()} />);

  fireEvent.click(screen.getByRole("button", { name: "核准" }));

  expect(onApprove).toHaveBeenCalledTimes(1);
});

test("駁回會展開備註表單，未填寫時確認按鈕停用", () => {
  render(<ReviewDialog onApprove={vi.fn()} onReject={vi.fn()} />);

  fireEvent.click(screen.getByRole("button", { name: "駁回" }));

  expect(screen.getByRole("button", { name: "確認駁回" })).toBeDisabled();
});

test("填寫備註後可以送出駁回", () => {
  const onReject = vi.fn();
  render(<ReviewDialog onApprove={vi.fn()} onReject={onReject} />);
  fireEvent.click(screen.getByRole("button", { name: "駁回" }));

  fireEvent.change(screen.getByPlaceholderText("請填寫駁回原因"), { target: { value: "證據不足" } });
  fireEvent.click(screen.getByRole("button", { name: "確認駁回" }));

  expect(onReject).toHaveBeenCalledWith("證據不足");
});

test("取消駁回會收合表單", () => {
  render(<ReviewDialog onApprove={vi.fn()} onReject={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "駁回" }));

  fireEvent.click(screen.getByRole("button", { name: "取消" }));

  expect(screen.getByRole("button", { name: "核准" })).toBeInTheDocument();
});
