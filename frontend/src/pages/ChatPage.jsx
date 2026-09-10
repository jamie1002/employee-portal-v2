import { useState } from "react";
import { askChat } from "../api/chat.api";
import ChatMessage from "../components/ChatMessage";

// 取自黃金題庫的代表題，涵蓋四份語料的主題，只是空狀態的提示按鈕，
// 不是精確題庫比對，實際答案一律由 AI 助理即時檢索回答。
const SUGGESTED_QUESTIONS = [
  "「應到班時間」跟「表定上班時間」有什麼不一樣？",
  "特別休假的天數怎麼計算？",
  "加班費用怎麼申請？",
  "公司的產品有哪些保固方案？",
];

function errorMessageFor(err) {
  const code = err.response?.data?.error?.code;
  if (code === "CHAT_UNAVAILABLE") {
    return "AI 助理目前無法使用（可能是展示環境尚未設定金鑰或語料），請稍後再試。";
  }
  if (code === "CHAT_RATE_LIMITED") {
    return "提問太頻繁了，請稍等一下再問。";
  }
  return err.response?.data?.error?.message ?? "發送失敗，請稍後再試。";
}

let messageSeq = 0;
function nextMessageId() {
  messageSeq += 1;
  return messageSeq;
}

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function sendQuestion(rawQuestion) {
    const question = rawQuestion.trim();
    if (!question || isSubmitting) return;

    setMessages((prev) => [...prev, { id: nextMessageId(), role: "user", text: question }]);
    setInput("");
    setIsSubmitting(true);

    try {
      const { answer } = await askChat(question);
      setMessages((prev) => [...prev, { id: nextMessageId(), role: "assistant", answer }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextMessageId(),
          role: "assistant",
          answer: { kind: "policy", text: errorMessageFor(err), refused: true, sources: [] },
        },
      ]);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendQuestion(input);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-xl font-medium text-text-primary">AI 助理</h2>
        <p className="mt-1 text-xs text-text-muted">
          回答僅依據公司政策文件。個人出勤紀錄、假別剩餘量與申請進度請至對應功能頁查詢。
        </p>
      </div>

      <div
        aria-live="polite"
        className="glass-panel min-h-[320px] flex-1 space-y-3 overflow-y-auto rounded-xl p-4"
      >
        {messages.length === 0 ? (
          <div className="space-y-3">
            <p className="text-sm text-text-secondary">試著問看看：</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED_QUESTIONS.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => sendQuestion(question)}
                  className="rounded-full border border-border-subtle bg-surface-800 px-3 py-1.5 text-xs text-text-secondary hover:border-accent-500 hover:text-accent-400"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) =>
            message.role === "user" ? (
              <ChatMessage key={message.id} role="user" text={message.text} />
            ) : (
              <ChatMessage key={message.id} role="assistant" answer={message.answer} />
            ),
          )
        )}
        {isSubmitting && <p className="text-xs text-text-muted">思考中…</p>}
      </div>

      <div className="flex items-end gap-2">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isSubmitting}
          rows={2}
          placeholder="輸入你的問題，Enter 送出、Shift+Enter 換行"
          className="flex-1 resize-none rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => sendQuestion(input)}
          disabled={isSubmitting || !input.trim()}
          className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-900 disabled:opacity-50"
        >
          {isSubmitting ? "思考中…" : "送出"}
        </button>
      </div>
    </div>
  );
}
