"""重測 `RETRIEVAL_MIN_SCORE` 的門檻校準腳本。從
`employee-portal-chatbot`（第一階段原型）的 `scripts/measure_min_score.py` 搬移。

**為什麼要有這支腳本**：`RETRIEVAL_MIN_SCORE` 是綁死在特定 embedding 模型 + 維度 +
正規化策略 + task_type 這一整組設定上的經驗值。只要換模型、換維度、或改動
`task_type`／正規化策略，這個值就作廢，必須重跑本腳本（見
`openspec/changes/add-policy-chat/design.md` Decision 1 與風險 9）。

三組樣本：

1. **真實問題**（題庫中 `expect_refusal` 不為 true 者）——門檻**絕對不能**切到這組的 top-1。
2. **主題相鄰的誘導題**（題庫中 `expect_refusal: true` 者）——分數會與第 1 組重疊，
   本來就擋不掉，靠生成端硬約束處理。這裡只量分布。
3. **完全離題**——寫在本檔 `OFF_TOPIC_QUESTIONS`，與語料毫無關係。門檻**應該**全部擋掉。

一律以 `min_score=-1` 執行（不過濾），看的是原始分數分布。

用法：

    python -m eval.measure_min_score                 # 全題庫
    python -m eval.measure_min_score --limit 10      # 只跑前 10 題真實問題，快速抽測
    python -m eval.measure_min_score --sleep 0.5     # 撞到免費層速率限制時放慢
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import asyncpg
import yaml

# Windows 主控台預設編碼不是 UTF-8，見 run_eval.py 同一個問題的說明。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.database import create_pool  # noqa: E402
from app.config.settings import app_settings  # noqa: E402
from app.repositories import policy_repository  # noqa: E402
from app.services.policy_retrieval import RetrievalResult  # noqa: E402
from app.utils.gemini import GeminiUnavailable, get_gemini_client  # noqa: E402

QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.yaml"

# 完全離題的對照組：刻意涵蓋不同語域（天氣、金融、技術、生活），避免只用一題就把
# 門檻校在單一問句的偶然分數上。
OFF_TOPIC_QUESTIONS = [
    "今天台北天氣如何？",
    "公司的股票代號是多少？",
    "Python 的 list 跟 tuple 有什麼差別？",
    "附近有沒有推薦的午餐餐廳？",
    "美金兌新台幣現在的匯率是多少？",
    "最近有什麼好看的電影？",
]

_QUOTA_RETRIES = 3
_QUOTA_RETRY_WAIT = 30


async def _top1_score(pool: asyncpg.Pool, client, query: str) -> tuple[float, str, str]:
    """回傳這個問題的 top-1（分數、來源檔、章節）。完全不套用門檻過濾。"""
    for attempt in range(_QUOTA_RETRIES):
        try:
            vector = await client.embed_query(query)
            rows = await policy_repository.search_similar(pool, vector, app_settings.RETRIEVAL_TOP_K)
            results = [RetrievalResult(**row) for row in rows]
            break
        except GeminiUnavailable as exc:
            message = str(exc)
            if "429" not in message and "quota" not in message.lower():
                raise
            if attempt == _QUOTA_RETRIES - 1:
                raise
            print(f"    （撞到速率限制，{_QUOTA_RETRY_WAIT} 秒後重試）")
            await asyncio.sleep(_QUOTA_RETRY_WAIT)
    if not results:
        return (float("nan"), "-", "（無結果）")
    top = results[0]
    return (top.score, top.source_file, top.section_path)


async def _measure(
    pool: asyncpg.Pool, client, label: str, questions: list[str], sleep: float
) -> list[tuple[float, str, str, str]]:
    """量測一組問題的 top-1 分數，回傳 (分數, 問題, 來源檔, 章節) 的列表。"""
    print(f"\n=== {label}（{len(questions)} 題）===")
    rows = []
    for index, question in enumerate(questions, start=1):
        score, source_file, section_path = await _top1_score(pool, client, question)
        rows.append((score, question, source_file, section_path))
        print(f"  [{index}/{len(questions)}] {score:.4f}  {question[:34]}")
        if sleep:
            time.sleep(sleep)
    return rows


def _describe(label: str, rows: list[tuple[float, str, str, str]]) -> None:
    """列出一組樣本的分數分布：最低、最高、中位數，以及最低的三題（門檻的風險邊緣）。"""
    scores = sorted(row[0] for row in rows)
    if not scores:
        return
    median = scores[len(scores) // 2]
    print(f"\n--- {label} 分布 ---")
    print(f"  最低 {scores[0]:.4f}　中位 {median:.4f}　最高 {scores[-1]:.4f}")
    print("  分數最低的三題（門檻若設在這之上就會誤傷）：")
    for score, question, source_file, section_path in sorted(rows)[:3]:
        print(f"    {score:.4f}  {question[:30]}  → {source_file} {section_path[:40]}")


def _sweep(
    real: list[tuple[float, str, str, str]],
    lure: list[tuple[float, str, str, str]],
    off_topic: list[tuple[float, str, str, str]],
) -> None:
    """門檻掃描表：每個候選門檻各自誤傷幾題真實問題、放行幾題誘導題與離題問題。

    判讀方式：**先看「誤傷真實問題」必須是 0**，再從中挑「擋掉離題問題」最多的那個值。
    誘導題那一欄擋不完是預期內的，不是選門檻的依據。
    """
    print("\n=== 門檻掃描 ===")
    print("  門檻 | 誤傷真實問題 | 未擋下的誘導題 | 未擋下的離題問題")
    print("  ---- | ------------ | -------------- | ----------------")
    threshold = 0.50
    while threshold <= 0.751:
        hurt = sum(1 for score, *_ in real if score < threshold)
        lure_pass = sum(1 for score, *_ in lure if score >= threshold)
        off_pass = sum(1 for score, *_ in off_topic if score >= threshold)
        flag = "  <- 誤傷" if hurt else ""
        print(
            f"  {threshold:.2f} | {hurt:>3}/{len(real):<8} | "
            f"{lure_pass:>3}/{len(lure):<10} | {off_pass:>3}/{len(off_topic)}{flag}"
        )
        threshold += 0.025


async def main_async(limit: int | None, sleep: float) -> None:
    data = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    # 權限題組的答案來自工具與權限判斷，不是語料的某一節，跟檢索門檻無關：放進「真實問題」
    # 會逼門檻去遷就一個本來就撈不到東西的問題，放進誘導題則會汙染分數重疊區間。
    items = [
        i for i in data["questions"] if i.get("category") not in ("permission", "personal", "chitchat")
    ]
    real_questions = [i["question"] for i in items if not i.get("expect_refusal")]
    lure_questions = [i["question"] for i in items if i.get("expect_refusal")]
    if limit:
        real_questions = real_questions[:limit]

    client = get_gemini_client()
    pool = await create_pool(app_settings.DATABASE_URL)
    try:
        real = await _measure(pool, client, "真實問題 top-1", real_questions, sleep)
        lure = await _measure(pool, client, "主題相鄰的誘導題 top-1", lure_questions, sleep)
        off_topic = await _measure(pool, client, "完全離題 top-1", OFF_TOPIC_QUESTIONS, sleep)
    finally:
        await pool.close()

    _describe("真實問題", real)
    _describe("主題相鄰的誘導題", lure)
    _describe("完全離題", off_topic)
    _sweep(real, lure, off_topic)


def main() -> None:
    parser = argparse.ArgumentParser(description="重測 RETRIEVAL_MIN_SCORE 的門檻校準腳本")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 題真實問題（快速抽測）")
    parser.add_argument("--sleep", type=float, default=0.0, help="每題之間睡幾秒，避開速率限制")
    args = parser.parse_args()
    asyncio.run(main_async(args.limit, args.sleep))


if __name__ == "__main__":
    main()
