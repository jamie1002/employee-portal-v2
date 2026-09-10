"""系統提示的防迴歸檢查：確保規則 5（輸出格式）與規則 6（防注入）沒有被意外刪除或改寫。"""

from app.services import chat_prompt
from app.services.policy_retrieval import RetrievalResult


def test_system_prompt_forbids_tables_and_numbered_lists():
    assert "表格" in chat_prompt.SYSTEM_PROMPT
    assert "數字清單" in chat_prompt.SYSTEM_PROMPT


def test_system_prompt_has_injection_defense_rule():
    assert "不是新的指令" in chat_prompt.SYSTEM_PROMPT


def test_system_prompt_allows_derivation_but_requires_sourced_basis():
    """第二版刻意開放「依據來自文件的推算」。這個測試守住的是**不要再被改回
    一刀切禁止**——第一版禁止推算，導致語料明明寫著「09:11 才算遲到」，模型仍
    不敢回答「9:20 算不算遲到」，助理形同文件複讀機。"""
    assert "可以推算" in chat_prompt.SYSTEM_PROMPT
    # 底線仍在：推算的依據必須來自提供的資料，不得憑空發明
    assert "不得憑空發明" in chat_prompt.SYSTEM_PROMPT
    # 推算過的答案必須提醒以系統為準
    assert "以系統顯示為準" in chat_prompt.SYSTEM_PROMPT


def test_fallback_prompt_forbids_stating_any_policy_content():
    """落空路徑沒有任何檢索依據，一旦讓模型講出具體規定就是純幻覺。"""
    assert "絕對禁止" in chat_prompt.FALLBACK_PROMPT
    assert "編造" in chat_prompt.FALLBACK_PROMPT
    # 三種要處理的情境都要在
    assert "早安" in chat_prompt.FALLBACK_PROMPT
    assert "情緒發洩" in chat_prompt.FALLBACK_PROMPT
    assert "人資" in chat_prompt.FALLBACK_PROMPT


def test_format_settings_uses_live_values_and_degrades_safely():
    text = chat_prompt.format_settings(
        {
            "work_start_time": "08:30:00",
            "work_end_time": "17:30:00",
            "lunch_start_time": "12:30:00",
            "lunch_end_time": "13:30:00",
            "grace_period_minutes": 15,
        }
    )
    assert "08:30" in text and "17:30" in text and "15 分鐘" in text
    assert "08:30:00" not in text  # 秒數截掉，不要讓模型照抄冗長格式

    # 讀不到設定時明講，不要餵可能過期的預設值讓模型誤以為是即時值
    degraded = chat_prompt.format_settings(None)
    assert "無法取得系統設定" in degraded


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
