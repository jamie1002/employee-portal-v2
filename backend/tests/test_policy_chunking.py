"""切段（從 employee-portal-chatbot 原型逐字搬移的邏輯，見 policy_chunking.py）。"""

import app.services.policy_chunking as chunking
from app.services.policy_chunking import chunk_markdown


def test_table_not_split_into_multiple_chunks():
    text = """# 測試公司 — 測試文件

## 1. 章節

| 欄位A | 欄位B |
| --- | --- |
| 值1 | 值2 |
| 值3 | 值4 |
"""
    chunks = chunk_markdown("test.md", text)

    assert len(chunks) == 1
    assert "欄位A" in chunks[0].raw_content
    assert "值3" in chunks[0].raw_content


def test_section_path_format_includes_document_title_and_headings():
    text = """# 測試公司 — 測試文件

## 1. 章節

### 1.1 子章節

內容文字
"""
    chunks = chunk_markdown("test.md", text)

    assert chunks[0].section_path == "測試文件 > 1. 章節 > 1.1 子章節"
    assert chunks[0].content.startswith("【測試文件 > 1. 章節 > 1.1 子章節】")


def test_qa_section_each_question_becomes_one_chunk(monkeypatch):
    monkeypatch.setattr(chunking, "QA_SECTIONS", {("test.md", "6. 常見情境 Q&A")})
    text = """# 測試公司 — 測試文件

## 6. 常見情境 Q&A

**Q：第一題？**
A：第一答。

**Q：第二題？**
A：第二答。
"""
    chunks = chunking.chunk_markdown("test.md", text)

    assert len(chunks) == 2
    assert "第一題" in chunks[0].raw_content and "第二題" not in chunks[0].raw_content
    assert "第二題" in chunks[1].raw_content and "第一題" not in chunks[1].raw_content


def test_non_qa_section_is_not_split_per_question():
    text = """# 測試公司 — 測試文件

## 6. 常見情境 Q&A

**Q：第一題？**
A：第一答。

**Q：第二題？**
A：第二答。
"""
    chunks = chunk_markdown("test.md", text)

    # 沒有把 ("test.md", "6. 常見情境 Q&A") 加進 QA_SECTIONS，兩題應合併在同一個 chunk。
    assert len(chunks) == 1
