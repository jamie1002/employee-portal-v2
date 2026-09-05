import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import DatePickerField from "./DatePickerField";

function Harness({ initialValue = "", initialViewDate = "2026-08-24" }) {
  const [value, setValue] = useState(initialValue);
  return (
    <DatePickerField
      id="test-date"
      label="日期"
      value={value}
      onChange={setValue}
      initialViewDate={initialViewDate}
    />
  );
}

test("關閉時顯示「不限日期」佔位文字，不顯示行事曆", () => {
  render(<Harness />);

  expect(screen.getByRole("button", { name: "不限日期" })).toBeInTheDocument();
  expect(screen.queryByText("清除")).not.toBeInTheDocument();
});

test("欄位空白時點開日曆，一律顯示 initialViewDate 所在月份，不是瀏覽器的真實現在時間", () => {
  render(<Harness initialViewDate="2026-08-24" />);

  fireEvent.click(screen.getByRole("button", { name: "不限日期" }));

  expect(screen.getByText("2026 年 8 月")).toBeInTheDocument();
});

test("已有值時點開日曆，顯示該值所在月份並標記選取狀態", () => {
  render(<Harness initialValue="2026-06-10" initialViewDate="2026-08-24" />);

  fireEvent.click(screen.getByRole("button", { name: "2026-06-10" }));

  expect(screen.getByText("2026 年 6 月")).toBeInTheDocument();
});

test("點選日期會回填欄位值並關閉行事曆", () => {
  render(<Harness initialViewDate="2026-08-24" />);
  fireEvent.click(screen.getByRole("button", { name: "不限日期" }));

  fireEvent.click(screen.getByRole("button", { name: "15" }));

  expect(screen.getByRole("button", { name: "2026-08-15" })).toBeInTheDocument();
  expect(screen.queryByText("2026 年 8 月")).not.toBeInTheDocument();
});

test("上一頁／下一頁月份切換", () => {
  render(<Harness initialViewDate="2026-08-24" />);
  fireEvent.click(screen.getByRole("button", { name: "不限日期" }));

  fireEvent.click(screen.getByRole("button", { name: "上個月" }));
  expect(screen.getByText("2026 年 7 月")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "下個月" }));
  fireEvent.click(screen.getByRole("button", { name: "下個月" }));
  expect(screen.getByText("2026 年 9 月")).toBeInTheDocument();
});

test("已有值時可以按「清除」清空欄位", () => {
  render(<Harness initialValue="2026-06-10" initialViewDate="2026-08-24" />);
  fireEvent.click(screen.getByRole("button", { name: "2026-06-10" }));

  fireEvent.click(screen.getByRole("button", { name: "清除" }));

  expect(screen.getByRole("button", { name: "不限日期" })).toBeInTheDocument();
});

test("按 Escape 會關閉行事曆", () => {
  render(<Harness initialViewDate="2026-08-24" />);
  fireEvent.click(screen.getByRole("button", { name: "不限日期" }));
  expect(screen.getByText("2026 年 8 月")).toBeInTheDocument();

  fireEvent.keyDown(document, { key: "Escape" });

  expect(screen.queryByText("2026 年 8 月")).not.toBeInTheDocument();
});

test("點擊元件外部會關閉行事曆", () => {
  render(
    <div>
      <Harness initialViewDate="2026-08-24" />
      <button type="button">外部按鈕</button>
    </div>,
  );
  fireEvent.click(screen.getByRole("button", { name: "不限日期" }));

  fireEvent.mouseDown(screen.getByRole("button", { name: "外部按鈕" }));

  expect(screen.queryByText("2026 年 8 月")).not.toBeInTheDocument();
});

test("initialViewDate 非同步取得（掛載時為 null）時，一旦拿到值就補上正確的瀏覽月份", () => {
  const { rerender } = render(
    <DatePickerField id="test-date" label="日期" value="" onChange={() => {}} initialViewDate={null} />,
  );

  rerender(<DatePickerField id="test-date" label="日期" value="" onChange={() => {}} initialViewDate="2026-08-24" />);
  fireEvent.click(screen.getByRole("button", { name: "不限日期" }));

  expect(screen.getByText("2026 年 8 月")).toBeInTheDocument();
});
