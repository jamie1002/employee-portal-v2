import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import ChatPage from "./ChatPage";

const mockAskChat = vi.fn();
vi.mock("../api/chat.api", () => ({
  askChat: (...args) => mockAskChat(...args),
}));

let mockUser = { id: 3, name: "陳小華", role: "employee", permissions: [] };
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

beforeEach(() => {
  mockUser = { id: 3, name: "陳小華", role: "employee", permissions: [] };
  mockAskChat.mockReset();
});

function getTextarea() {
  return screen.getByPlaceholderText("輸入你的問題，Enter 送出、Shift+Enter 換行");
}

test("送出問題後顯示回答與依據來源", async () => {
  mockAskChat.mockResolvedValue({
    answer: {
      kind: "policy",
      text: "特別休假滿一年可休 7 日。\n\n— 依據：leave-policy.md 2.1 特別休假級距",
      refused: false,
      sources: [],
    },
  });
  render(<ChatPage />);

  fireEvent.change(getTextarea(), { target: { value: "特別休假怎麼算？" } });
  fireEvent.click(screen.getByRole("button", { name: "送出" }));

  expect(await screen.findByText(/特別休假滿一年可休 7 日/)).toBeInTheDocument();
  // 「— 依據：」一律不顯示給使用者：模型仍會輸出（eval 靠它驗證答案有所本），
  // 但那是給開發與自動驗證看的，掛在對話裡不像人在講話。
  expect(screen.queryByText(/依據：/)).not.toBeInTheDocument();
  expect(screen.queryByText(/leave-policy\.md/)).not.toBeInTheDocument();
  expect(mockAskChat).toHaveBeenCalledWith("特別休假怎麼算？");
});

test("CHAT_UNAVAILABLE 顯示專屬文案", async () => {
  mockAskChat.mockRejectedValue({ response: { data: { error: { code: "CHAT_UNAVAILABLE" } } } });
  render(<ChatPage />);

  fireEvent.change(getTextarea(), { target: { value: "問題" } });
  fireEvent.click(screen.getByRole("button", { name: "送出" }));

  expect(await screen.findByText(/AI 助理目前無法使用/)).toBeInTheDocument();
});

test("CHAT_RATE_LIMITED 顯示專屬文案", async () => {
  mockAskChat.mockRejectedValue({ response: { data: { error: { code: "CHAT_RATE_LIMITED" } } } });
  render(<ChatPage />);

  fireEvent.change(getTextarea(), { target: { value: "問題" } });
  fireEvent.click(screen.getByRole("button", { name: "送出" }));

  expect(await screen.findByText(/提問太頻繁/)).toBeInTheDocument();
});

test("送出中按鈕 disabled 且文字變成「思考中…」", async () => {
  let resolveAsk;
  mockAskChat.mockReturnValue(
    new Promise((resolve) => {
      resolveAsk = resolve;
    }),
  );
  render(<ChatPage />);

  fireEvent.change(getTextarea(), { target: { value: "問題" } });
  fireEvent.click(screen.getByRole("button", { name: "送出" }));

  const thinkingButton = await screen.findByRole("button", { name: "思考中…" });
  expect(thinkingButton).toBeDisabled();
  expect(getTextarea()).toBeDisabled();

  resolveAsk({ answer: { kind: "policy", text: "答案", refused: false, sources: [] } });
});

test("空白輸入不會呼叫 API", () => {
  render(<ChatPage />);

  fireEvent.change(getTextarea(), { target: { value: "   " } });
  fireEvent.click(screen.getByRole("button", { name: "送出" }));

  expect(mockAskChat).not.toHaveBeenCalled();
});

test("點擊建議問題直接送出", async () => {
  mockAskChat.mockResolvedValue({
    answer: { kind: "policy", text: "答案內容", refused: false, sources: [] },
  });
  render(<ChatPage />);

  fireEvent.click(screen.getByText("「應到班時間」跟「表定上班時間」有什麼不一樣？"));

  await screen.findByText("答案內容");
  expect(mockAskChat).toHaveBeenCalledWith("「應到班時間」跟「表定上班時間」有什麼不一樣？");
});

test("Enter 送出、Shift+Enter 換行不送出", () => {
  mockAskChat.mockResolvedValue({ answer: { kind: "policy", text: "答案", refused: false, sources: [] } });
  render(<ChatPage />);
  const textarea = getTextarea();

  fireEvent.change(textarea, { target: { value: "問題內容" } });
  fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
  expect(mockAskChat).not.toHaveBeenCalled();

  fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
  expect(mockAskChat).toHaveBeenCalledWith("問題內容");
});


// ── 批 B：免責文案與依角色的建議問題 ────────────────────────────────────────

test("不再顯示「請至對應功能頁查詢」的免責文案（批 A 埋的伏筆已拆除）", () => {
  render(<ChatPage />);

  expect(screen.queryByText(/請至對應功能頁查詢/)).not.toBeInTheDocument();
});

test("一般員工的建議問題只含個人與政策題，不含團隊題", () => {
  render(<ChatPage />);

  expect(screen.getByRole("button", { name: "我今天打卡了嗎？" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /誰遲到最多/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /等我審核/ })).not.toBeInTheDocument();
});

test("主管的建議問題含部門範圍的題目", () => {
  mockUser = { id: 2, name: "王小明", role: "manager", department_id: 1, permissions: [] };
  render(<ChatPage />);

  expect(screen.getByRole("button", { name: "我部門這個月誰遲到最多？" })).toBeInTheDocument();
});

test("管理員的建議問題含全公司範圍的題目", () => {
  mockUser = { id: 1, name: "系統管理者", role: "admin", permissions: [] };
  render(<ChatPage />);

  expect(screen.getByRole("button", { name: "這個月全公司誰缺勤最多？" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /我部門這個月/ })).not.toBeInTheDocument();
});

test("kind 為 personal 的回答正常渲染", async () => {
  mockAskChat.mockResolvedValue({
    answer: { kind: "personal", text: "你今天還沒打卡喔。", refused: false, sources: [] },
  });
  render(<ChatPage />);

  fireEvent.change(getTextarea(), { target: { value: "我今天打卡了嗎" } });
  fireEvent.click(screen.getByRole("button", { name: "送出" }));

  expect(await screen.findByText("你今天還沒打卡喔。")).toBeInTheDocument();
});
