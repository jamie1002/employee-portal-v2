import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import ChatMessage from "./ChatMessage";

describe("ChatMessage", () => {
  test("使用者訊息直接顯示文字", () => {
    render(<ChatMessage role="user" text="特別休假怎麼算？" />);

    expect(screen.getByText("特別休假怎麼算？")).toBeInTheDocument();
  });

  test("渲染回答內容，但一律剝除「依據」行不顯示給使用者", () => {
    const answer = {
      kind: "policy",
      text: "特別休假滿一年可休 7 日。\n\n— 依據：leave-policy.md 2.1 特別休假級距",
      refused: false,
      sources: [],
    };

    render(<ChatMessage role="assistant" answer={answer} />);

    expect(screen.getByText(/特別休假滿一年可休 7 日/)).toBeInTheDocument();
    expect(screen.queryByText(/依據：/)).not.toBeInTheDocument();
    expect(screen.queryByText(/leave-policy\.md/)).not.toBeInTheDocument();
  });

  test("fallback（檢索落空的寒暄／同理回應）同樣走 markdown 渲染", () => {
    const answer = {
      kind: "fallback",
      text: "早安！我可以幫你查公司的出勤規定、請假辦法這類問題。",
      refused: true,
      sources: [],
    };

    render(<ChatMessage role="assistant" answer={answer} />);

    expect(screen.getByText(/早安！我可以幫你查公司的出勤規定/)).toBeInTheDocument();
  });

  test("拒答時沒有依據 chips", () => {
    const answer = { kind: "policy", text: "文件中查無相關規定。", refused: true, sources: [] };

    render(<ChatMessage role="assistant" answer={answer} />);

    expect(screen.getByText("文件中查無相關規定。")).toBeInTheDocument();
    expect(screen.queryByText(/依據：/)).not.toBeInTheDocument();
  });

  test("未知 kind 時退回顯示原始文字，不崩潰", () => {
    const answer = { kind: "unknown", text: "備援文字", refused: false, sources: [] };

    render(<ChatMessage role="assistant" answer={answer} />);

    expect(screen.getByText("備援文字")).toBeInTheDocument();
  });
});
