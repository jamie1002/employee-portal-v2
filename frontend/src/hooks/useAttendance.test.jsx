import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { useAttendance } from "./useAttendance";

const mockApi = vi.hoisted(() => ({
  getToday: vi.fn(),
  punchIn: vi.fn(),
  punchOut: vi.fn(),
}));
vi.mock("../api/attendance.api", () => mockApi);

function Probe() {
  const { today, isLoading, error, punchIn } = useAttendance();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="status">{today?.status ?? "none"}</span>
      <span data-testid="error">{error ?? "none"}</span>
      <button onClick={punchIn}>punch-in</button>
    </div>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.getToday.mockResolvedValue({ attendance: { status: null, has_punched_in: false } });
});

test("掛載時載入今日狀態", async () => {
  render(<Probe />);

  await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
  expect(mockApi.getToday).toHaveBeenCalledTimes(1);
});

test("打卡成功後直接以回應更新狀態，不必重新載入", async () => {
  mockApi.punchIn.mockResolvedValue({ attendance: { status: "normal", has_punched_in: true } });
  render(<Probe />);
  await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

  fireEvent.click(screen.getByText("punch-in"));

  await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("normal"));
  expect(mockApi.getToday).toHaveBeenCalledTimes(1);
});

test("打卡失敗時顯示後端訊息並重新同步今日狀態", async () => {
  mockApi.punchIn.mockRejectedValue({
    response: { data: { error: { message: "今日已完成上班打卡。" } } },
  });
  render(<Probe />);
  await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

  fireEvent.click(screen.getByText("punch-in"));

  await waitFor(() => expect(screen.getByTestId("error").textContent).toBe("今日已完成上班打卡。"));
  expect(mockApi.getToday).toHaveBeenCalledTimes(2);
});

test("連點兩次只會送出一次請求", async () => {
  let resolvePunch;
  mockApi.punchIn.mockReturnValue(
    new Promise((resolve) => {
      resolvePunch = resolve;
    }),
  );
  render(<Probe />);
  await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

  const button = screen.getByText("punch-in");
  fireEvent.click(button);
  fireEvent.click(button);

  expect(mockApi.punchIn).toHaveBeenCalledTimes(1);
  resolvePunch({ attendance: { status: "normal" } });
});
