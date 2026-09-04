import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import PermissionPanel from "./PermissionPanel";

test("勾選未選取的權限會把該鍵加進 selected", () => {
  const onChange = vi.fn();
  render(<PermissionPanel selected={[]} onChange={onChange} onClose={vi.fn()} />);

  fireEvent.click(screen.getByLabelText("國定假日管理"));

  expect(onChange).toHaveBeenCalledWith(["holidays.manage"]);
});

test("取消勾選已選取的權限會把該鍵移除", () => {
  const onChange = vi.fn();
  render(<PermissionPanel selected={["holidays.manage", "settings.manage"]} onChange={onChange} onClose={vi.fn()} />);

  fireEvent.click(screen.getByLabelText("國定假日管理"));

  expect(onChange).toHaveBeenCalledWith(["settings.manage"]);
});

test("點完成會呼叫 onClose", () => {
  const onClose = vi.fn();
  render(<PermissionPanel selected={[]} onChange={vi.fn()} onClose={onClose} />);

  fireEvent.click(screen.getByRole("button", { name: "完成" }));

  expect(onClose).toHaveBeenCalled();
});
