// AI 回答的前處理：`SimpleMarkdown` 不支援表格與 `1.` 數字清單（見
// components/SimpleMarkdown.jsx 的說明），系統提示規則 5 已要求模型不要輸出這些格式，
// 這裡是最後一道保險——把模型偶爾自己加的數字清單降級成 `-` 條列，並把回答結尾的
// 「— 依據：」引用行切出來，改用 chips 呈現（結構化資訊，比一行小字清楚，也讓 e2e
// 好斷言），不讓它們進 SimpleMarkdown 的段落渲染。

const NUMBERED_LIST_RE = /^(\s*)\d+[.)]\s+(.*)$/;
const CITATION_LINE_RE = /^—\s*依據[：:]\s*(.+)$/;

export function demoteNumberedLists(text) {
  return text
    .split("\n")
    .map((line) => {
      const match = line.match(NUMBERED_LIST_RE);
      return match ? `${match[1]}- ${match[2]}` : line;
    })
    .join("\n");
}

export function splitCitations(text) {
  const bodyLines = [];
  const citations = [];

  for (const line of text.split("\n")) {
    const match = line.trim().match(CITATION_LINE_RE);
    if (match) {
      citations.push(match[1].trim());
    } else {
      bodyLines.push(line);
    }
  }

  while (bodyLines.length > 0 && bodyLines[bodyLines.length - 1].trim() === "") {
    bodyLines.pop();
  }

  return { body: bodyLines.join("\n"), citations };
}

export function prepareChatMarkdown(text) {
  const { body, citations } = splitCitations(text);
  return { body: demoteNumberedLists(body), citations };
}
