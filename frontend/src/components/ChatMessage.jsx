import { SimpleMarkdown } from "./SimpleMarkdown";
import { prepareChatMarkdown } from "../utils/chatMarkdown";

export default function ChatMessage({ role, answer, text }) {
  const isUser = role === "user";

  // 「— 依據：」那幾行**一律剝除不顯示**。模型仍然被要求輸出它（系統提示規則 4），
  // 因為那是 eval「引用率 100%」門檻用來自動驗證「答案確實有所本、不是模型瞎編」
  // 的唯一機制；但對使用者來說，每則回答後面掛一行「根據某文件第幾節」不像人在
  // 對話，比較像查字典，所以只留在後端資料裡給開發與驗證用。
  const bodyText = isUser ? text : prepareChatMarkdown(answer.text).body;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${
          isUser ? "bg-accent-500/20 text-text-primary" : "glass-panel text-text-secondary"
        }`}
      >
        {isUser ? <p className="text-text-primary">{bodyText}</p> : <SimpleMarkdown source={bodyText} />}
      </div>
    </div>
  );
}
