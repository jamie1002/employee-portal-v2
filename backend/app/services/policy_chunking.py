"""切段模組：把 `db/policy_docs/` 下的 Markdown 語料切成適合檢索的 chunk。

從 `employee-portal-chatbot`（第一階段原型）的 `src/chunking.py` 逐字搬移，只改了
語料目錄常數（`DOCS_DIR`）與本段落的路徑引用。核心邏輯完全不變，設計依據見該專案的
`SPEC.md` §5「切段策略」。核心原則：
- 以 `##` / `###` 標題為切段邊界，維護標題堆疊產生 section_path。
- 表格與引言區塊（`>` 開頭）視為不可切開的整體。
- 特定 Q&A 章節每一題自成一個 chunk。
- 章節內容過長時以「段落」為單位二次切分，每段仍帶同一個 section_path。

`section_path` 格式為「文件主題簡稱 > 章節 > 子章節」，文件主題簡稱取自文件標題
（H1）中「——」之後的部分（例如「暖丘生活股份有限公司 — 請假辦法及福利制度」→
「請假辦法及福利制度」）。這個格式對齊 `db/migrations/002_policy_embeddings.sql` 中
`section_path` 欄位註解給出的範例。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# db/policy_docs/ 固定在專案根目錄下（backend/app/services/ 往上四層）。
DOCS_DIR = Path(__file__).resolve().parents[3] / "db" / "policy_docs"

# 章節累積內容超過此字數時，以段落為單位二次切分（約略值）。
MAX_SECTION_CHARS = 1200

# 需要套用「每一題自成一個 chunk」規則的章節，key 為 (檔名, 章節標題文字)。
QA_SECTIONS = {
    ("leave-policy.md", "6. 常見情境 Q&A"),
    ("product-catalog.md", "4. 常見情境 Q&A"),
}

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
_BLOCKQUOTE_LINE_RE = re.compile(r"^\s*>")
_QA_QUESTION_RE = re.compile(r"^\*\*Q[：:]")


@dataclass
class Chunk:
    """一個切段結果。"""

    source_file: str
    """來源檔名，例如 `leave-policy.md`。"""

    chunk_index: int
    """同一份文件內的切段序號，從 0 起。"""

    section_path: str
    """「文件主題簡稱 > 章節 > 子章節」的完整路徑，是回答引用來源的唯一依據。"""

    raw_content: str
    """未加 context prefix 的原始段落文字，供人工逐句對照驗收使用。"""

    content: str
    """實際送去 embedding 與送進 LLM 的文字，開頭已含 `【section_path】` 這個 context prefix。"""


def _classify_line(line: str) -> str:
    """把一行文字分類成 blank / table / quote / text 四種之一。"""
    if line.strip() == "":
        return "blank"
    if _TABLE_LINE_RE.match(line):
        return "table"
    if _BLOCKQUOTE_LINE_RE.match(line):
        return "quote"
    return "text"


def _group_paragraph_blocks(lines: list[str]) -> list[str]:
    """把一個章節底下的所有行，依「空行」與「種類切換」分成段落區塊。

    表格（table）與引言區塊（quote）各自視為不可再切開的整體：即使引言內部
    以單獨的 `>` 作為段落分隔（而非真正的空行），仍會被歸在同一個區塊裡。
    """
    blocks: list[str] = []
    current: list[str] = []
    current_kind: str | None = None

    def flush() -> None:
        nonlocal current, current_kind
        if current:
            blocks.append("\n".join(current))
        current = []
        current_kind = None

    for line in lines:
        kind = _classify_line(line)
        if kind == "blank":
            flush()
            continue
        if current_kind is not None and kind != current_kind:
            flush()
        current.append(line)
        current_kind = kind

    flush()
    return blocks


def _greedy_group(blocks: list[str], limit: int = MAX_SECTION_CHARS) -> list[str]:
    """把段落區塊依序合併，每組字數不超過 `limit`（單一區塊本身超過也不強拆）。"""
    groups: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in blocks:
        added_len = len(block) + (2 if current else 0)  # 區塊間以 "\n\n" 相接
        if current and current_len + added_len > limit:
            groups.append("\n\n".join(current))
            current = []
            current_len = 0
            added_len = len(block)
        current.append(block)
        current_len += added_len

    if current:
        groups.append("\n\n".join(current))
    return groups


def _split_qa_blocks(lines: list[str]) -> list[str]:
    """把 Q&A 章節的內容依「**Q：」切成一題一個區塊（問句＋完整回答）。"""
    raw_blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if _QA_QUESTION_RE.match(line.strip()):
            if current:
                raw_blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        raw_blocks.append(current)

    result: list[str] = []
    for block in raw_blocks:
        while block and block[0].strip() == "":
            block.pop(0)
        while block and block[-1].strip() == "":
            block.pop()
        if block:
            result.append("\n".join(block))
    return result


def _parse_sections(body_lines: list[str]) -> list[tuple[list[str], list[str]]]:
    """依 `##`/`###` 標題把（去掉 H1 之後的）內容切成 (標題堆疊, 內容行) 的序列。

    第一個標題出現之前的內容，會以 `heading_path == []` 的形式排在結果最前面，
    交由呼叫端決定如何處理（本模組的策略是併入第一個章節，見 `chunk_markdown`）。
    """
    sections: list[tuple[list[str], list[str]]] = []
    heading_path: list[str] = []
    current_body: list[str] = []

    for line in body_lines:
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) in (2, 3):
            sections.append((list(heading_path), current_body))
            current_body = []
            level = len(match.group(1))
            text = match.group(2).strip()
            if level == 2:
                heading_path = [text]
            else:
                if not heading_path:
                    raise ValueError(
                        f"### 子章節「{text}」出現在任何 ## 章節之前，語料結構異常"
                    )
                heading_path = [heading_path[0], text]
        else:
            current_body.append(line)

    sections.append((list(heading_path), current_body))
    return sections


def _document_short_title(full_title: str) -> str:
    """從完整文件標題取出「主題簡稱」（去掉公司名稱字首）。

    對齊 db/migrations/002_policy_embeddings.sql 中 section_path 欄位註解的範例格式：
    「暖丘生活股份有限公司 — 請假辦法及福利制度」→「請假辦法及福利制度」。
    """
    if "—" in full_title:
        return full_title.rsplit("—", 1)[-1].strip()
    return full_title.strip()


def chunk_markdown(source_file: str, text: str) -> list[Chunk]:
    """把單一份 Markdown 語料切成 chunk 列表。"""
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError(f"{source_file}：第一行必須是文件標題（# 開頭）")

    full_title = lines[0][2:].strip()
    document_short_title = _document_short_title(full_title)

    sections = _parse_sections(lines[1:])

    # 文件開頭（H1 之後、第一個 ## 之前）的引言 blockquote 併入第一個章節，
    # 不獨立成 chunk。
    if sections and sections[0][0] == []:
        _, intro_body = sections.pop(0)
        if intro_body:
            if not sections:
                raise ValueError(f"{source_file}：只有前言、沒有任何章節")
            first_path, first_body = sections[0]
            sections[0] = (first_path, [*intro_body, "", *first_body])

    chunks: list[Chunk] = []
    for heading_path, body_lines in sections:
        if not heading_path:
            continue
        if not any(line.strip() for line in body_lines):
            # 章節底下沒有直接內容（內容全在更深一層的子章節裡），不產生 chunk。
            continue

        section_path = " > ".join([document_short_title, *heading_path])
        is_qa_section = len(heading_path) == 1 and (source_file, heading_path[0]) in QA_SECTIONS

        if is_qa_section:
            raw_blocks = _split_qa_blocks(body_lines)
        else:
            blocks = _group_paragraph_blocks(body_lines)
            raw_blocks = _greedy_group(blocks)

        for raw in raw_blocks:
            chunks.append(
                Chunk(
                    source_file=source_file,
                    chunk_index=len(chunks),
                    section_path=section_path,
                    raw_content=raw,
                    content=f"【{section_path}】\n{raw}",
                )
            )

    return chunks


def chunk_all_documents(docs_dir: Path = DOCS_DIR) -> list[Chunk]:
    """切段 docs/ 目錄下所有 Markdown 語料，依檔名排序以確保結果穩定可重現。"""
    all_chunks: list[Chunk] = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        all_chunks.extend(chunk_markdown(path.name, text))
    return all_chunks
