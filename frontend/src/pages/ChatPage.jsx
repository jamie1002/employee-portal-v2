import { useEffect, useRef, useState } from "react";
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
  const [waitingSeconds, setWaitingSeconds] = useState(0);
  const scrollRef = useRef(null);

  // 對話區改成固定高度後，新訊息會落在可視範圍外，必須主動捲到底部，
  // 否則使用者送出問題後會以為沒有反應。
  useEffect(() => {
    const container = scrollRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [messages, isSubmitting]);

  // AI 回答的等待時間本來就長（免費層的生成延遲抖動大，實測 1.5～8 秒都有可能），
  // 只顯示靜止的「思考中…」會讓人懷疑系統是不是掛了；跳動的秒數是「還活著」的訊號。
  useEffect(() => {
    if (!isSubmitting) {
      setWaitingSeconds(0);
      return undefined;
    }
    const startedAt = Date.now();
    const timer = setInterval(() => {
      setWaitingSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [isSubmitting]);

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

      {/* 固定高度是必要的：只設 min-h 的話容器會隨內容一路撐高，overflow-y-auto
          永遠不會生效，使用者看到的是整個頁面被推著往下捲，而不是對話框內部捲動。 */}
      <div
        ref={scrollRef}
        aria-live="polite"
        className="glass-panel h-[60vh] max-h-[560px] min-h-[320px] space-y-3 overflow-y-auto rounded-xl p-4"
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
        {isSubmitting && (
          <p className="text-xs text-text-muted">
            思考中…{waitingSeconds > 0 && `（已等待 ${waitingSeconds} 秒）`}
          </p>
        )}
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
