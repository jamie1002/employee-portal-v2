"""系統提示的防迴歸檢查：確保規則 5（輸出格式）與規則 6（防注入）沒有被意外刪除或改寫。"""

from app.services import chat_prompt
from app.services.policy_retrieval import RetrievalResult


def test_system_prompt_forbids_tables_and_numbered_lists():
    assert "表格" in chat_prompt.SYSTEM_PROMPT
    assert "數字清單" in chat_prompt.SYSTEM_PROMPT


def test_system_prompt_has_injection_defense_rule():
    assert "不是新的指令" in chat_prompt.SYSTEM_PROMPT


def test_is_refusal_recognizes_standard_and_corpus_specific_markers():
    assert chat_prompt.is_refusal("文件中查無相關規定。")
    assert chat_prompt.is_refusal("本文件不包含庫存資料，請洽詢庫存系統。")
    assert not chat_prompt.is_refusal("特別休假滿一年可休 7 日。\n\n— 依據：leave-policy.md 2.1")


def test_format_context_includes_source_file_and_section_path():
    results = [RetrievalResult(source_file="a.md", section_path="A > 1", content="內容", score=0.9)]

    context = chat_prompt.format_context(results)

    assert "a.md" in context
    assert "A > 1" in context
    assert "內容" in context


def test_build_user_content_preserves_literal_braces_in_context():
    """context 或 question 裡若剛好含有大括號字元，.format() 只替換模板本身的
    {context}/{question} 兩個欄位，不會誤把資料內容裡的花括號當成模板欄位。"""
    results = [RetrievalResult(source_file="a.md", section_path="A > 1", content="範例：{x}", score=0.9)]

    user_content = chat_prompt.build_user_content(results, "問題裡也有 {y} 這種字元")

    assert "{x}" in user_content
    assert "{y}" in user_content
