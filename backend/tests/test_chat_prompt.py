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


# ── 批 B：工具規則的結構性約束 ──────────────────────────────────────────────

def test_first_round_prompt_never_mentions_skipping_the_disclaimer():
    """**這條測試守的是一次實測出來的退化**：第一版把「工具數字不要加但書」寫進
    規則 7，結果 77 題 eval 的推算但書從 7/7 掉到 1/7——那句否定句位在提示詞最後，
    位置上壓過前面的規則 2，模型連純政策推算的答案也不加但書了。

    修法是讓政策路徑結構上看不到那句話。這條測試確保它不會被改回去。
    """
    from datetime import date

    first_round = chat_prompt.build_system_prompt(date(2026, 9, 11))

    assert "不要對這些數字加" not in first_round
    assert chat_prompt.TOOL_RESULT_RULES not in first_round
    # 規則 2 的但書要求必須還在。
    assert "以系統顯示為準" in first_round


def test_second_round_prompt_adds_the_tool_result_rules():
    from datetime import date

    second_round = chat_prompt.build_system_prompt(date(2026, 9, 11), with_tool_results=True)

    assert chat_prompt.TOOL_RESULT_RULES in second_round


def test_prompt_without_today_falls_back_to_batch_a():
    """拿不到虛擬時鐘的日期時退回批 A 的提示：沒有「今天」卻叫模型用工具查區間，
    它只會用自己認知的年份去猜，查出來是空的，然後很自然地說「你那個月沒有紀錄」。"""
    assert chat_prompt.build_system_prompt(None) == chat_prompt.SYSTEM_PROMPT


def test_today_is_rendered_with_weekday():
    from datetime import date

    prompt = chat_prompt.build_system_prompt(date(2026, 9, 11))

    assert "2026-09-11" in prompt
    assert "星期五" in prompt


# ── 拒答判定的寬鬆度與誤判防線 ──────────────────────────────────────────────

def test_refusal_detection_tolerates_filler_words():
    """語氣改自然之後，模型會在「文件」與「沒有」之間插入修飾語。固定字串比對
    會把這種標準的正確拒答判成「該拒答卻回答了」（實測 eval 因此假紅一題）。

    下面四句是**同一題誘導題在四輪 eval 中實際產生的回答**——模型每次都正確拒答，
    措辭卻每次不同。這就是為什麼拒答偵測不能只認一種寫法。
    """
    assert chat_prompt.is_refusal("關於今年的員工旅遊，公司文件裡目前沒有寫到具體的地點喔。")
    assert chat_prompt.is_refusal("這部分公司文件裡沒有寫到。")
    assert chat_prompt.is_refusal("文件中沒有提到這個主題。")
    assert chat_prompt.is_refusal("公司文件並未提到相關規定。")
    assert chat_prompt.is_refusal(
        "關於員工旅遊的資訊，目前公司文件裡只有提到補助比例的規定，"
        "並沒有寫到今年要去哪裡玩，或是具體的活動日期。"
    )


def test_refusal_detection_keeps_corpus_authored_phrasings():
    """語料自己寫的拒答措辭（product-catalog.md §4／§5）必須照樣認得。"""
    assert chat_prompt.is_refusal("本文件不包含庫存資料。")
    assert chat_prompt.is_refusal("這個問題不在本文件範圍。")
    assert chat_prompt.is_refusal("查無相關規定。")


def test_refusal_detection_does_not_flag_normal_answers():
    """誤判成拒答比漏判更糟：拒答率會虛高，引用率的分母還會跟著縮水。
    特別是「規定沒有上限」這種句子，開頭詞刻意不收「規定」就是為了擋這個。"""
    assert not chat_prompt.is_refusal("公假的規定沒有上限，依實際需要核給。")
    assert not chat_prompt.is_refusal("加班時數以 30 分鐘為單位無條件捨去。")
    assert not chat_prompt.is_refusal("你八月遲到 3 次。")
    assert not chat_prompt.is_refusal("依照文件的說明，滿 10 年有 16 天特休。")
