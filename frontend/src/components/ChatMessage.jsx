import { SimpleMarkdown } from "./SimpleMarkdown";
import { prepareChatMarkdown } from "../utils/chatMarkdown";

// 目前只有 "policy" 一種 kind（政策問答）。批 B 加入個人資料查詢工具時，這裡會依
// answer.kind 分支渲染不同的呈現方式，政策分支維持原封不動（見
// openspec/changes/add-policy-chat/design.md「為批 B 鋪路」）。
function PolicyAnswer({ answer }) {
  const { body, citations } = prepareChatMarkdown(answer.text);

  return (
    <div className="space-y-2">
      <SimpleMarkdown source={body} />
      {citations.length > 0 && (
        <div className="flex flex-wrap gap-2 pt-1">
          {citations.map((citation) => (
            <span
              key={citation}
              className="rounded-full border border-accent-500/50 bg-surface-800 px-2.5 py-1 text-xs text-accent-400"
            >
              依據：{citation}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatMessage({ role, answer, text }) {
  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${
          isUser ? "bg-accent-500/20 text-text-primary" : "glass-panel text-text-secondary"
        }`}
      >
        {isUser ? (
          <p className="text-text-primary">{text}</p>
        ) : answer.kind === "policy" ? (
          <PolicyAnswer answer={answer} />
        ) : (
          <p>{answer.text}</p>
        )}
      </div>
    </div>
  );
}
