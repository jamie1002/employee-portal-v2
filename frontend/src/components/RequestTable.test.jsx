import { render, screen } from "@testing-library/react";
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

test("依 columns 定義呈現欄位，render 優先於直接讀值", () => {
  render(<RequestTable records={[{ id: 1, reason: "忘記打卡", status: "pending" }]} columns={COLUMNS} />);

  expect(screen.getByText("忘記打卡")).toBeInTheDocument();
  expect(screen.getByText("狀態：pending")).toBeInTheDocument();
});

test("缺值欄位顯示破折號", () => {
  render(<RequestTable records={[{ id: 1, reason: null, status: "pending" }]} columns={COLUMNS} />);

  expect(screen.getByText("—")).toBeInTheDocument();
});
