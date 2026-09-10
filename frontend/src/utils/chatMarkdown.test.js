import { describe, expect, test } from "vitest";
import { demoteNumberedLists, prepareChatMarkdown, splitCitations } from "./chatMarkdown";

describe("demoteNumberedLists", () => {
  test("把 `1. ` 開頭的行降級成 `- `", () => {
    const input = "1. 第一步\n2. 第二步";
    expect(demoteNumberedLists(input)).toBe("- 第一步\n- 第二步");
  });

  test("把 `1) ` 開頭的行也降級成 `- `", () => {
    expect(demoteNumberedLists("1) 第一步")).toBe("- 第一步");
  });

  test("非數字清單的行維持不變", () => {
    const input = "一般段落文字\n- 既有的條列項目";
    expect(demoteNumberedLists(input)).toBe(input);
  });
});

describe("splitCitations", () => {
  test("切出結尾的依據行，本文不含依據行", () => {
    const text = "特別休假滿一年可休 7 日。\n\n— 依據：leave-policy.md 2. 假別與額度 > 2.1 特別休假級距";

    const { body, citations } = splitCitations(text);

    expect(body).toBe("特別休假滿一年可休 7 日。");
    expect(citations).toEqual(["leave-policy.md 2. 假別與額度 > 2.1 特別休假級距"]);
  });

  test("採用多個片段時每一行依據各自切出", () => {
    const text = "答案內容。\n— 依據：a.md 章節一\n— 依據：b.md 章節二";

    const { citations } = splitCitations(text);

    expect(citations).toEqual(["a.md 章節一", "b.md 章節二"]);
  });

  test("沒有依據行時 citations 為空陣列，本文不變", () => {
    const text = "文件中查無相關規定。";

    const { body, citations } = splitCitations(text);

    expect(body).toBe(text);
    expect(citations).toEqual([]);
  });
});

describe("prepareChatMarkdown", () => {
  test("同時套用數字清單降級與依據切分", () => {
    const text = "先做以下事項：\n1. 第一步\n2. 第二步\n\n— 依據：a.md 章節";

    const { body, citations } = prepareChatMarkdown(text);

    expect(body).toBe("先做以下事項：\n- 第一步\n- 第二步");
    expect(citations).toEqual(["a.md 章節"]);
  });
});
