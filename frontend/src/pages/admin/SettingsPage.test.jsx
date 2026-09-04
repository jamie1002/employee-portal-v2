import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import SettingsPage from "./SettingsPage";

const mockGetSettings = vi.fn();
const mockUpdateSettings = vi.fn();
vi.mock("../../api/settings.api", () => ({
  getSettings: (...args) => mockGetSettings(...args),
  updateSettings: (...args) => mockUpdateSettings(...args),
}));

let mockUser = { id: 1, name: "系統管理者", role: "admin", permissions: [] };
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

const DEFAULT_SETTINGS = {
  work_start_time: "09:00:00", work_end_time: "18:00:00",
  lunch_start_time: "12:00:00", lunch_end_time: "13:00:00",
  grace_period_minutes: 10,
};

beforeEach(() => {
  mockUser = { id: 1, name: "系統管理者", role: "admin", permissions: [] };
  mockGetSettings.mockReset().mockResolvedValue({ settings: DEFAULT_SETTINGS });
  mockUpdateSettings.mockReset();
});

test("載入後把後端的 HH:mm:ss 值轉成 HH:mm 顯示在輸入框", async () => {
  render(<SettingsPage />);

  await waitFor(() => expect(screen.getByLabelText("上班時間")).toHaveValue("09:00"));
});

test("前端違反上班<午休開始<午休結束<下班時擋下，不呼叫 API", async () => {
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByLabelText("上班時間")).toHaveValue("09:00"));

  fireEvent.change(screen.getByLabelText("午休開始"), { target: { value: "08:00" } });
  fireEvent.click(screen.getByRole("button", { name: "儲存設定" }));

  expect(mockUpdateSettings).not.toHaveBeenCalled();
  expect(screen.getByText(/考勤時段設定不合理/)).toBeInTheDocument();
});

test("成功送出後顯示設定已更新並以後端回傳值回填", async () => {
  mockUpdateSettings.mockResolvedValue({
    settings: { ...DEFAULT_SETTINGS, work_start_time: "08:30:00", grace_period_minutes: 15 },
  });
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByLabelText("上班時間")).toHaveValue("09:00"));

  fireEvent.change(screen.getByLabelText("上班時間"), { target: { value: "08:30" } });
  fireEvent.change(screen.getByLabelText("緩衝時間（分鐘）"), { target: { value: "15" } });
  fireEvent.click(screen.getByRole("button", { name: "儲存設定" }));

  await waitFor(() => expect(screen.getByText("設定已更新")).toBeInTheDocument());
  expect(screen.getByLabelText("上班時間")).toHaveValue("08:30");
});
