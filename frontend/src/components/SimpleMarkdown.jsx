// 極簡、安全的 Markdown 渲染：僅支援標題／清單／粗體／行內代碼／段落，一律經 React
// 輸出轉義，刻意不用 dangerouslySetInnerHTML（見 CLAUDE.md 安全規則）與第三方 markdown 套件。
function renderInline(text, keyPrefix) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={`${keyPrefix}-${index}`} className="font-semibold text-text-primary">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={`${keyPrefix}-${index}`} className="rounded bg-surface-800 px-1 py-0.5 text-xs">
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={`${keyPrefix}-${index}`}>{part}</span>;
  });
}

export function SimpleMarkdown({ source }) {
  const lines = source.split("\n");
  const blocks = [];
  let listBuffer = [];
  let paragraphBuffer = [];

  // 標準 Markdown 段落語意：同一段落的內容常常在原始檔案裡手動換行，空行才代表段落
  // 真正結束。把「每一行」都當成獨立段落會把一段連貫文字拆成好幾個帶間距的 <p>。
  function flushParagraph(key) {
    if (paragraphBuffer.length > 0) {
      const text = paragraphBuffer.join(" ");
      blocks.push(
        <p key={`p-${key}`} className="text-sm text-text-secondary">
          {renderInline(text, key)}
        </p>,
      );
      paragraphBuffer = [];
    }
  }

  function flushList(key) {
    if (listBuffer.length > 0) {
      blocks.push(
        <ul key={`list-${key}`} className="ml-5 list-disc space-y-1 text-sm text-text-secondary">
          {listBuffer.map((item, i) => (
            <li key={i}>{renderInline(item, `li-${key}-${i}`)}</li>
          ))}
        </ul>,
      );
      listBuffer = [];
    }
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim();

    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      flushParagraph(index);
      listBuffer.push(trimmed.slice(2));
      return;
    }

    if (trimmed === "" || trimmed === "---") {
      flushList(index);
      flushParagraph(index);
      return;
    }

    if (trimmed.startsWith("### ") || trimmed.startsWith("## ") || trimmed.startsWith("# ") || trimmed.startsWith(">")) {
      flushList(index);
      flushParagraph(index);

      if (trimmed.startsWith("### ")) {
        blocks.push(
          <h4 key={index} className="mt-3 text-sm font-semibold text-text-primary">
            {renderInline(trimmed.slice(4), index)}
          </h4>,
        );
      } else if (trimmed.startsWith("## ")) {
        blocks.push(
          <h3 key={index} className="mt-4 text-base font-semibold text-accent-400">
            {renderInline(trimmed.slice(3), index)}
          </h3>,
        );
      } else if (trimmed.startsWith("# ")) {
        blocks.push(
          <h2 key={index} className="mt-2 text-lg font-semibold text-text-primary">
            {renderInline(trimmed.slice(2), index)}
          </h2>,
        );
      } else {
        blocks.push(
          <p key={index} className="border-l-2 border-border-subtle pl-3 text-sm italic text-text-muted">
            {renderInline(trimmed.replace(/^>\s*/, ""), index)}
          </p>,
        );
      }
      return;
    }

    // 一般文字行：清單項目的續行併回上一個清單項，否則累積進段落緩衝。
    if (listBuffer.length > 0) {
      listBuffer[listBuffer.length - 1] += ` ${trimmed}`;
    } else {
      paragraphBuffer.push(trimmed);
    }
  });
  flushList("end");
  flushParagraph("end");

  return <div className="space-y-2">{blocks}</div>;
}
