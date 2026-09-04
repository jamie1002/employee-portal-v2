import { render, screen, within } from "@testing-library/react";
import RequestTable from "./RequestTable";

const COLUMNS = [
  { key: "id", label: "編號" },
  { key: "reason", label: "理由" },
  { key: "status", label: "狀態", render: (r) => `狀態：${r.status}` },
];

test("沒有紀錄時顯示空狀態文字", () => {
  render(<RequestTable records={[]} columns={COLUMNS} emptyMessage="尚無資料" />);

  expect(screen.getByText("尚無資料")).toBeInTheDocument();
});

test("依 columns 定義呈現欄位，render 優先於直接讀值（桌機表格版）", () => {
  render(<RequestTable records={[{ id: 1, reason: "忘記打卡", status: "pending" }]} columns={COLUMNS} />);

  const table = within(screen.getByRole("table"));
  expect(table.getByText("忘記打卡")).toBeInTheDocument();
  expect(table.getByText("狀態：pending")).toBeInTheDocument();
});

test("依 columns 定義呈現欄位（手機卡片版）", () => {
  render(<RequestTable records={[{ id: 1, reason: "忘記打卡", status: "pending" }]} columns={COLUMNS} />);

  const cards = within(screen.getByTestId("request-cards"));
  expect(cards.getByText("忘記打卡")).toBeInTheDocument();
  expect(cards.getByText("狀態：pending")).toBeInTheDocument();
});

test("缺值欄位顯示破折號", () => {
  render(<RequestTable records={[{ id: 1, reason: null, status: "pending" }]} columns={COLUMNS} />);

  expect(screen.getAllByText("—").length).toBeGreaterThan(0);
});
