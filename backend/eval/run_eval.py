"""黃金題庫評估腳本。從 `employee-portal-chatbot`（第一階段原型）的 `eval/run_eval.py`
搬移，改動點：拿掉載入 v2 業務函式的 `sys.path` hack（現在是同一個專案內部，直接
import）、檢索與生成改呼叫新的 service（`policy_retrieval` / `chat_prompt` /
`app.utils.gemini`）、節流已移進 `gemini.py` 的行程級節流所以拿掉
`InMemoryRateLimiter`（429 重試邏輯保留，只是判斷條件改看例外訊息字串，因為
`gemini.py` 把所有上游例外統一包成 `GeminiUnavailable`，型別名稱不再是
`ResourceExhausted`）。`--skip-generation`、`--limit`、`--save-answers` 全部保留，
新增 `--category` 供批 B 只跑個人資料題組快速迭代。

量測的指標：

| 指標 | 來源 | 門檻 |
| :--- | :--- | :--- |
| hit@1 / hit@3 | 檢索層 | hit@3 ≥ 90% |
| 語料寫死的數字與 v2 業務函式一致 | ground truth | 100% |
| 回答附引用來源比率 | 生成 | 100% |
| 誘導題拒答率 | 生成 | 100% |
| 數字型答案與 v2 函式輸出一致 | 生成 | 100% |

生成端三項會真的呼叫 Gemini（每題一次）。只想量檢索層、不想燒 API 額度時加
`--skip-generation`。

**引用率的分母刻意排除拒答的回答**：拒答本來就沒有可引用的來源，把它算進分母會讓
「正確拒答」反而拉低引用率。誘導題的正確性由「誘導題拒答率」那一項負責。

**數字型題目的 ground truth 一律不手填**：`questions.yaml` 只宣告要呼叫哪個函式、帶
什麼參數，實際數值在這裡即時 import 本專案的業務函式算出。語料被改壞或 v2 規則變更
時，`in_corpus: true` 的一致性檢查會立刻紅。

**第二版：開放推算之後，數字檢查的方向整個反過來了。** 第一版禁止模型做任何推算，
所以「語料沒寫的數字」出現在回答裡就算失敗；實測發現這個約束過度到損害功能——語料
白紙黑字寫著「09:11:00 才算遲到」，問「9:20 算不算遲到」卻答不出來。現在改成兩個
獨立的欄位判斷：

- `in_corpus`：語料有沒有白紙黑字寫這個數字 → 決定要不要做「語料 vs v2 業務函式」
  的一致性檢查（這一項驗證的是語料本身沒寫錯，與回答無關）
- `expect_stated`：回答該不該講出這個數字 → `required`（依據都在資料裡，模型應該
  推算出來並講明）／`optional`（前提不明確，例如不知道是哪一週、中間有沒有國定假日）

**推算題另外多一道但書檢查**：語料沒寫死、由模型推算出來的答案，必須附上「以系統
實際顯示為準」這類提醒——推算的前提（當天班表、請假狀況）可能與使用者的實際情形
不同，沒有這句提醒，使用者會把推算結果當成系統的正式判定。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from time import monotonic  # 注意：上面的 `time` 是 datetime.time，不是 time 模組

import asyncpg
import yaml

# Windows 主控台預設編碼不是 UTF-8，報告裡的「≥」等符號會直接讓 print() 拋
# UnicodeEncodeError 中斷整輪評估（見 app/db_scripts/migrate.py 的同一慣例）。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.database import create_pool  # noqa: E402
from app.config.settings import app_settings  # noqa: E402
from app.repositories import policy_repository  # noqa: E402
from app.services import chat_prompt  # noqa: E402
from app.services import settings as settings_service  # noqa: E402
from app.services.leave_hours import calculate_leave_hours, calculate_overtime_hours  # noqa: E402
from app.services.leave_quota import special_leave_days  # noqa: E402
from app.services.policy_retrieval import RetrievalResult  # noqa: E402
from app.services.work_hours import WorkSettings  # noqa: E402
from app.utils.gemini import GeminiUnavailable, get_gemini_client  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.yaml"

HIT3_THRESHOLD = 0.9
TZ = "Asia/Taipei"

# 免費層每分鐘節流（429）是暫時性的，等一下再送就會過。gemini.py 已經主動節流，
# 這裡再加一層重試，避免整輪 72 題只因為一次暫時性節流就整份驗收變紅。
_QUOTA_RETRIES = 3
_QUOTA_RETRY_WAIT = 30

# 檢索落空的內部標記：eval 不為這條路徑呼叫 API（見下方說明）。
_NO_CONTEXT_MARKER = "（檢索落空，未呼叫政策問答生成）"

# 推算型答案必須附上的但書。措辭不強制統一，只要有表達「以系統實際顯示為準」
# 的意思即可，所以比對幾種常見說法而不是單一字串。
_DISCLAIMER_MARKERS = ("系統顯示為準", "系統實際顯示", "以系統為準", "系統顯示的為準", "系統實際判定")

_GROUND_TRUTH_FUNCTIONS = {
    "calculate_leave_hours": calculate_leave_hours,
    "calculate_overtime_hours": calculate_overtime_hours,
    "special_leave_days": special_leave_days,
}

# 與 v2 自己的單元測試、種子資料一致的考勤設定（見 SPEC.md §5.4 預設值）。
# v2 的 system_settings 若被調整，這裡與語料都要同步修改（語料異動紀律）。
_GROUND_TRUTH_SETTINGS = WorkSettings(
    work_start=time(9, 0),
    work_end=time(18, 0),
    lunch_start=time(12, 0),
    lunch_end=time(13, 0),
    grace_minutes=10,
)


def _taipei(value: str) -> datetime:
    """把 questions.yaml 裡的本地時間字串轉成帶台北時區的 datetime。"""
    return datetime.fromisoformat(f"{value}+08:00")


def _format_number(value: float | int) -> str:
    """把 ground truth 數值格式化成語料中會出現的寫法（3.0 → 3、14 → 14）。"""
    return f"{value:g}"


# 單位的同義寫法。語料的級距表寫「14 日」，但模型在自然對話時會講「14 天」——
# 第一版語氣生硬時模型傾向照抄語料用字，語氣改自然之後就改用口語說法了。
# 只比對單一字串會把「答對了但換個說法」誤判成失敗（實測一輪因此假紅 4 題）。
_UNIT_SYNONYMS = {
    "日": ("日", "天"),
    "天": ("日", "天"),
    "小時": ("小時", "個小時"),
}


def _number_variants(value: float | int, unit: str) -> tuple[str, ...]:
    """產生可接受的數值寫法（含單位同義詞與有無空格的差異）。"""
    number = _format_number(value)
    units = _UNIT_SYNONYMS.get(unit, (unit,)) if unit else ("",)
    variants: list[str] = []
    for candidate in units:
        variants.append(f"{number} {candidate}".strip())
        variants.append(f"{number}{candidate}")
    return tuple(dict.fromkeys(variants))


@dataclass
class QuestionResult:
    question: str
    expected_section_path: str | None
    expect_refusal: bool
    top_paths: list[str] = field(default_factory=list)
    top_scores: list[float] = field(default_factory=list)
    hit_at_1: bool | None = None
    hit_at_3: bool | None = None
    passed_filter_count: int = 0
    number_label: str | None = None
    number_ok: bool | None = None
    number_detail: str = ""
    number_in_corpus: bool | None = None
    """這個數字有沒有寫在語料裡，決定要不要做「語料 vs v2 函式」一致性檢查。"""

    expect_stated: str = "required"
    """回答該不該講出這個數字：`required`（依據都在資料裡，應該推算出來）／
    `optional`（前提不明確，例如不知道是哪一週、中間有沒有國定假日）。"""

    answer_has_disclaimer: bool | None = None
    """推算出來的答案有沒有加上「以系統顯示為準」這類但書（系統提示規則 2 的硬性要求）。"""

    should_be_answered: bool = True
    """這題是否「必須答得出來」。只有誘導題（expect_refusal）除外——語料真的沒有答案，
    本來就該拒答。第二版開放推算之後，推算題也必須答得出來（第一版把它們排除在這項
    檢查之外，等於默許助理對「9:20 算不算遲到」這類問題擺爛）。"""

    # --- 以下為生成端，--skip-generation 時全部維持 None ---
    answer_text: str | None = None
    answer_refused: bool | None = None
    answer_has_citation: bool | None = None
    answer_number_ok: bool | None = None
    answer_error: str | None = None


def _compute_ground_truth(spec: dict) -> float | int:
    """依 questions.yaml 的宣告，即時呼叫 v2 業務函式算出期望數值。"""
    function_name = spec["function"]
    kwargs = spec.get("kwargs", {})

    if function_name not in _GROUND_TRUTH_FUNCTIONS:
        raise SystemExit(f"questions.yaml 指定了未知的 ground truth 函式：{function_name}")
    function = _GROUND_TRUTH_FUNCTIONS[function_name]

    if function_name == "special_leave_days":
        return function(total_months=kwargs["total_months"])
    # calculate_leave_hours / calculate_overtime_hours 的簽名相同
    return function(_taipei(kwargs["start"]), _taipei(kwargs["end"]), _GROUND_TRUTH_SETTINGS, TZ)


async def _load_corpus_by_section_path(pool: asyncpg.Pool) -> dict[str, str]:
    """把資料庫裡的語料依 section_path 聚合，供「語料寫死的數字是否與 v2 一致」的檢查使用。"""
    rows = await pool.fetch("SELECT section_path, raw_content FROM policy_embeddings")
    corpus: dict[str, str] = {}
    for row in rows:
        corpus[row["section_path"]] = corpus.get(row["section_path"], "") + "\n" + row["raw_content"]
    return corpus


def _scrub(text: str) -> str:
    """把 API Key 從錯誤訊息裡抹掉——評估報告常常會被貼到別的地方。"""
    api_key = app_settings.GOOGLE_API_KEY.strip()
    return text.replace(api_key, "***") if api_key else text


async def _search_unfiltered(pool: asyncpg.Pool, client, question: str, top_k: int) -> list[RetrievalResult]:
    """量 hit@k 用的「未過濾的完整排序」，繞過 `policy_retrieval.retrieve()` 的門檻過濾——
    hit@k 衡量的是排序品質，門檻過濾屬於系統行為，另外以 passed_filter_count 記錄。"""
    vector = await client.embed_query(question)
    rows = await policy_repository.search_similar(pool, vector, top_k)
    return [RetrievalResult(**row) for row in rows]


async def run_eval(
    pool: asyncpg.Pool, questions: list[dict], with_generation: bool = True
) -> tuple[list[QuestionResult], dict[str, str]]:
    client = get_gemini_client()
    corpus = await _load_corpus_by_section_path(pool)
    # 與正式問答路徑一致：推算的基準取自系統當前生效的考勤設定，不是語料寫死的預設值。
    live_settings = await settings_service.get_settings(pool)
    results: list[QuestionResult] = []

    started_at = monotonic()
    for index, item in enumerate(questions, start=1):
        # 進度印到 stderr：報告本體走 stdout，重導向存檔時不會被進度訊息汙染。
        elapsed = monotonic() - started_at
        eta = ""
        if index > 1:
            remaining = elapsed / (index - 1) * (len(questions) - index + 1)
            eta = f" 預估剩餘 {remaining / 60:.1f} 分"
        print(
            f"[{datetime.now():%H:%M:%S}] [{index}/{len(questions)}]{eta} {item['question'][:36]}",
            file=sys.stderr,
            flush=True,
        )
        expected_path = item.get("expected_section_path")
        result = QuestionResult(
            question=item["question"],
            expected_section_path=expected_path,
            expect_refusal=bool(item.get("expect_refusal", False)),
            should_be_answered=not item.get("expect_refusal", False),
        )

        retrieved = await _search_unfiltered(pool, client, item["question"], max(3, app_settings.RETRIEVAL_TOP_K))
        result.top_paths = [r.section_path for r in retrieved]
        result.top_scores = [r.score for r in retrieved]
        result.passed_filter_count = sum(1 for r in retrieved if r.score >= app_settings.RETRIEVAL_MIN_SCORE)

        if expected_path:
            result.hit_at_1 = expected_path in result.top_paths[:1]
            result.hit_at_3 = expected_path in result.top_paths[:3]

        number_spec = item.get("expected_number")
        needle: str | None = None
        if number_spec:
            value = _compute_ground_truth(number_spec)
            unit = number_spec.get("unit", "")
            variants = _number_variants(value, unit)
            needle = variants[0]
            result.number_label = f"{number_spec['function']}{number_spec.get('kwargs', {})} = {needle}"
            result.number_in_corpus = bool(number_spec.get("in_corpus"))
            # `expect_stated` 與 `in_corpus` 是兩件獨立的事，第二版刻意拆開：
            #   in_corpus     語料有沒有白紙黑字寫這個數字 → 決定要不要做「語料 vs
            #                 v2 業務函式」的一致性檢查（驗證語料沒寫錯）
            #   expect_stated 回答該不該講出這個數字 → required（依據都在資料裡，
            #                 應該推算出來）／optional（前提不明確，講不講都可以）
            # 第一版只有 in_corpus，且語料沒寫就等於「回答不可出現」——那正是讓
            # 助理連「9:20 晚於 9:11」都不敢回答的根源。
            result.expect_stated = number_spec.get("expect_stated", "required")

            if number_spec.get("in_corpus") and expected_path:
                section_text = corpus.get(expected_path, "")
                result.number_ok = any(v in section_text for v in variants)
                result.number_detail = (
                    f"語料章節「{expected_path}」{'有' if result.number_ok else '找不到'}「{needle}」"
                )

        if with_generation:
            usable = [r for r in retrieved if r.score >= app_settings.RETRIEVAL_MIN_SCORE][
                : app_settings.RETRIEVAL_TOP_K
            ]

            generated_text: str | None = None
            for attempt in range(_QUOTA_RETRIES):
                try:
                    if not usable:
                        # 檢索落空：正式環境走 FALLBACK_PROMPT 生成自然回應，但 eval
                        # 不需要為此燒配額——這條路徑必定是拒答，指標上的意義只有
                        # 「誘導題有沒有被擋下」，直接標記即可。
                        generated_text = _NO_CONTEXT_MARKER
                        break
                    # 必須跟 `chat.py` 一樣注入系統當前生效的考勤設定——少了它，
                    # eval 測到的是一個「拿不到設定」的降級環境，模型會多講一句
                    # 「系統設定無法取得」，評出來的品質與正式路徑不一致。
                    user_content = chat_prompt.build_user_content(
                        usable, item["question"], live_settings
                    )
                    generated_text = await client.generate(chat_prompt.SYSTEM_PROMPT, user_content)
                    break
                except GeminiUnavailable as exc:
                    # 這個迴圈內能拋出 GeminiUnavailable 的原因（逾時、429、網路暫時性錯誤）
                    # 全部屬於外部依賴的暫時性問題——沒有金鑰的情況在迴圈外的
                    # get_gemini_client() 就已經先失敗，不會走到這裡。原本只針對 429／quota
                    # 字樣重試，漏掉了「呼叫 Gemini API 逾時。」這個訊息，導致偶發的單題逾時
                    # 直接判定失敗、整輪 72 題就地變紅（實測一輪 3 題因此失敗，不重試就沒有
                    # 機會證明只是暫時性延遲）。這裡只放寬 eval 腳本自己的重試範圍，
                    # 不影響正式環境 chat.py 的 25 秒逾時設定（那是刻意配合使用者體驗的值）。
                    is_transient_error = True
                    if is_transient_error and attempt < _QUOTA_RETRIES - 1:
                        print(
                            f"    撞到配額限制，{_QUOTA_RETRY_WAIT} 秒後重試（{attempt + 1}/{_QUOTA_RETRIES - 1}）",
                            file=sys.stderr,
                            flush=True,
                        )
                        await asyncio.sleep(_QUOTA_RETRY_WAIT)
                        continue
                    result.answer_error = _scrub(f"{type(exc).__name__}: {exc}")[:200]
                    break

            if generated_text is not None:
                result.answer_text = generated_text
                # 落空路徑不靠字串比對——那條路徑本來就沒有依據，必定是拒答。
                result.answer_refused = (
                    True if generated_text == _NO_CONTEXT_MARKER else chat_prompt.is_refusal(generated_text)
                )
                source_files = {source.source_file for source in usable}
                result.answer_has_citation = "依據：" in generated_text and any(
                    source_file in generated_text for source_file in source_files
                )
                if needle:
                    stated = any(v in generated_text for v in variants)
                    # required：依據都在資料裡，回答必須講出這個數字（且必須正確——
                    #           ground truth 是 v2 業務函式即時算出的，不是手填）
                    # optional：前提不明確，講不講都可以；但若講了就必須是對的
                    if result.expect_stated == "optional":
                        result.answer_number_ok = True
                    else:
                        result.answer_number_ok = stated

                    # 推算出來的答案必須附上但書。推算的前提（當天班表、請假狀況、
                    # 是哪一週）可能與使用者的實際情形不同，沒有這句提醒，使用者會
                    # 把推算結果當成系統的正式判定。
                    if not number_spec.get("in_corpus"):
                        result.answer_has_disclaimer = any(
                            marker in generated_text for marker in _DISCLAIMER_MARKERS
                        )

        results.append(result)

    return results, corpus


def _report(results: list[QuestionResult], corpus: dict[str, str]) -> bool:
    """列印評估報告，回傳是否通過驗收門檻。"""
    total = len(results)
    refusal_questions = [r for r in results if r.expect_refusal]
    scored = [r for r in results if r.expected_section_path]

    hit1 = sum(1 for r in scored if r.hit_at_1)
    hit3 = sum(1 for r in scored if r.hit_at_3)
    hit1_rate = hit1 / len(scored) if scored else 0.0
    hit3_rate = hit3 / len(scored) if scored else 0.0

    print("=" * 78)
    print("黃金題庫評估報告")
    print("=" * 78)
    print(f"題庫總題數：{total}（其中誘導題 {len(refusal_questions)} 題）")
    print(f"納入 hit@k 計算的題數：{len(scored)}（有標註 expected_section_path 的題目）")
    print()

    print("--- 檢索指標（不含生成）---")
    print(f"hit@1：{hit1}/{len(scored)} = {hit1_rate:.1%}")
    print(f"hit@3：{hit3}/{len(scored)} = {hit3_rate:.1%}  （門檻 ≥ {HIT3_THRESHOLD:.0%}）")
    print()

    misses = [r for r in scored if not r.hit_at_3]
    if misses:
        print(f"--- hit@3 未命中的 {len(misses)} 題（診斷用）---")
        for r in misses:
            print(f"Q：{r.question}")
            print(f"   期望：{r.expected_section_path}")
            for path, score in zip(r.top_paths[:3], r.top_scores[:3]):
                print(f"   實際：{score:.4f}  {path}")
            print()

    rank_misses = [r for r in scored if r.hit_at_3 and not r.hit_at_1]
    if rank_misses:
        print(f"--- hit@1 未命中但 hit@3 命中的 {len(rank_misses)} 題（章節內容重疊的線索）---")
        for r in rank_misses:
            print(f"Q：{r.question}")
            print(f"   期望：{r.expected_section_path}")
            print(f"   實際 top-1：{r.top_scores[0]:.4f}  {r.top_paths[0]}")
        print()

    print("--- 誘導題（語料沒有答案，期望拒答）---")
    filtered_empty = sum(1 for r in refusal_questions if r.passed_filter_count == 0)
    print(
        f"檢索層就被過濾成空的：{filtered_empty}/{len(refusal_questions)}"
        f"（門檻 RETRIEVAL_MIN_SCORE={app_settings.RETRIEVAL_MIN_SCORE}）"
    )
    for r in refusal_questions:
        top_score = r.top_scores[0] if r.top_scores else 0.0
        status = "檢索層已擋下" if r.passed_filter_count == 0 else "進入生成步驟，需靠生成端硬約束拒答"
        print(f"  [{top_score:.4f}] {status}｜{r.question}")
    print()

    number_results = [r for r in results if r.number_label]
    print(f"--- 數字型 ground truth（{len(number_results)} 題，一律由 v2 業務函式即時算出）---")
    corpus_failures = []
    for r in number_results:
        line = f"  {r.number_label}"
        if r.number_ok is True:
            line += f"　OK {r.number_detail}"
        elif r.number_ok is False:
            line += f"　FAIL {r.number_detail}"
            corpus_failures.append(r)
        else:
            line += "　（語料未寫死此數字，不做一致性檢查）"
        print(line)
    print()

    print("--- 章節覆蓋率 ---")
    covered = {r.expected_section_path for r in results if r.expected_section_path}
    all_paths = set(corpus.keys())
    uncovered = sorted(all_paths - covered)
    print(f"語料共 {len(all_paths)} 個 section_path，題庫涵蓋 {len(covered & all_paths)} 個")
    if uncovered:
        print(f"未被任何題目涵蓋的章節（{len(uncovered)} 個）：")
        for path in uncovered:
            print(f"  - {path}")
    print()

    generated = [r for r in results if r.answer_text is not None or r.answer_error]
    generation_failures: list[str] = []

    if not generated:
        print("--- 生成端指標 ---")
        print("（本次以 --skip-generation 執行，未呼叫 LLM）")
        print()
    else:
        errored = [r for r in generated if r.answer_error]
        answered = [r for r in generated if r.answer_text is not None]

        print(f"--- 生成端指標（實際呼叫 Gemini，{len(generated)} 題）---")
        if errored:
            print(f"呼叫失敗 {len(errored)} 題：")
            for r in errored[:5]:
                print(f"  {r.question} → {r.answer_error}")
            generation_failures.append(f"{len(errored)} 題呼叫 LLM 失敗")

        citable = [r for r in answered if not r.answer_refused]
        cited = sum(1 for r in citable if r.answer_has_citation)
        citation_rate = cited / len(citable) if citable else 1.0
        print(f"回答附引用來源比率：{cited}/{len(citable)} = {citation_rate:.1%}（門檻 100%，分母排除拒答）")
        for r in citable:
            if not r.answer_has_citation:
                print(f"  FAIL 未附引用：{r.question}")
        if cited != len(citable):
            generation_failures.append("有回答沒有附上引用來源")

        refusal_answered = [r for r in answered if r.expect_refusal]
        refused_ok = sum(1 for r in refusal_answered if r.answer_refused)
        refusal_rate = refused_ok / len(refusal_answered) if refusal_answered else 1.0
        print(f"誘導題拒答率：{refused_ok}/{len(refusal_answered)} = {refusal_rate:.1%}（門檻 100%）")
        for r in refusal_answered:
            if not r.answer_refused:
                print(f"  FAIL 該拒答卻回答了：{r.question}")
                print(f"     回答：{(r.answer_text or '')[:120]}")
        if refused_ok != len(refusal_answered):
            generation_failures.append("有誘導題沒有正確拒答")

        should_answer = [r for r in answered if r.should_be_answered]
        over_refused = [r for r in should_answer if r.answer_refused]
        answer_rate = (len(should_answer) - len(over_refused)) / len(should_answer) if should_answer else 1.0
        print(
            f"該答有答（未過度拒答）：{len(should_answer) - len(over_refused)}/{len(should_answer)} "
            f"= {answer_rate:.1%}（門檻 100%）"
        )
        for r in over_refused:
            print(f"  FAIL 語料有答案卻拒答了：{r.question}")
            print(f"     回答：{(r.answer_text or '')[:120]}")
        if over_refused:
            generation_failures.append(f"{len(over_refused)} 題語料有答案卻被拒答（過度拒答）")

        numeric_answered = [r for r in answered if r.answer_number_ok is not None]
        numeric_ok = sum(1 for r in numeric_answered if r.answer_number_ok)
        numeric_rate = numeric_ok / len(numeric_answered) if numeric_answered else 1.0
        print(
            f"數字型答案正確：{numeric_ok}/{len(numeric_answered)} = {numeric_rate:.1%}（門檻 100%）\n"
            "  （ground truth 一律由 v2 業務函式即時算出；expect_stated=required 的題目\n"
            "   回答必須講出這個數字，optional 的題目前提不明確、講不講都可以）"
        )
        for r in numeric_answered:
            if not r.answer_number_ok:
                print(f"  FAIL 回答沒有講出正確的推算結果（{r.number_label}）：{r.question}")
                print(f"     回答：{(r.answer_text or '')[:160]}")
        if numeric_ok != len(numeric_answered):
            generation_failures.append("有數字型答案與 v2 函式輸出不一致")

        # 推算題的但書檢查：推算的前提（當天班表、請假狀況、是哪一週）可能與使用者的
        # 實際情形不同，沒有這句提醒，使用者會把推算結果當成系統的正式判定。
        derived = [r for r in answered if r.answer_has_disclaimer is not None]
        with_disclaimer = sum(1 for r in derived if r.answer_has_disclaimer)
        disclaimer_rate = with_disclaimer / len(derived) if derived else 1.0
        print(
            f"推算型答案附上但書：{with_disclaimer}/{len(derived)} = {disclaimer_rate:.1%}（門檻 100%）\n"
            "  （語料沒有寫死、由模型推算出來的答案，必須提醒以系統實際顯示為準）"
        )
        for r in derived:
            if not r.answer_has_disclaimer:
                print(f"  FAIL 推算結果沒有附上「以系統顯示為準」的提醒：{r.question}")
                print(f"     回答：{(r.answer_text or '')[:160]}")
        if with_disclaimer != len(derived):
            generation_failures.append("有推算型答案沒有附上「以系統顯示為準」的但書")
        print()

    passed = (
        hit3_rate >= HIT3_THRESHOLD
        and not corpus_failures
        and not uncovered
        and not generation_failures
    )
    print("=" * 78)
    if passed:
        print("PASS 全部驗收項目通過")
    else:
        if hit3_rate < HIT3_THRESHOLD:
            print(f"FAIL hit@3 {hit3_rate:.1%} 未達門檻 {HIT3_THRESHOLD:.0%}")
        if corpus_failures:
            print(f"FAIL 有 {len(corpus_failures)} 題的語料數字與 v2 業務函式算出來的不一致")
        if uncovered:
            print(f"FAIL 有 {len(uncovered)} 個章節沒有被任何題目涵蓋")
        for failure in generation_failures:
            print(f"FAIL {failure}")
    print("=" * 78)
    return passed


def _format_answers_for_review(results: list[QuestionResult], questions: list[dict]) -> str:
    """把每題的期望要點與實際回答並排輸出，供人工／AI 逐句對照驗收使用。"""
    lines: list[str] = []
    for index, (result, item) in enumerate(zip(results, questions), start=1):
        lines.append("=" * 78)
        if result.expect_refusal:
            kind = "誘導題"
        elif result.number_label and not result.number_in_corpus:
            kind = "推算題"
        else:
            kind = "一般"
        lines.append(f"第 {index} 題　[{kind}]　{result.question}")
        lines.append(f"期望章節：{result.expected_section_path or '（語料無對應章節）'}")
        lines.append("期望要點：")
        for point in item.get("expected_points", []):
            lines.append(f"  - {point}")
        if result.number_label:
            direction = "回答必須講出" if result.expect_stated == "required" else "講不講都可以（前提不明確）"
            lines.append(f"數字 ground truth：{result.number_label}（{direction}）")
        lines.append("-" * 78)
        lines.append(result.answer_text or f"（無回答：{result.answer_error or '未執行生成'}）")
        lines.append("")
    return "\n".join(lines)


async def _main_async(args: argparse.Namespace) -> bool:
    data = yaml.safe_load(args.questions.read_text(encoding="utf-8"))
    questions = data["questions"]
    if args.category:
        questions = [q for q in questions if q.get("category") == args.category]
    if args.limit:
        questions = questions[: args.limit]

    pool = await create_pool(app_settings.DATABASE_URL)
    try:
        results, corpus = await run_eval(pool, questions, with_generation=not args.skip_generation)
    finally:
        await pool.close()

    if args.save_answers:
        args.save_answers.write_text(_format_answers_for_review(results, questions), encoding="utf-8")
        print(f"已將 {len(results)} 題的回答寫入 {args.save_answers}（供逐句對照驗收）\n")

    return _report(results, corpus)


def main() -> None:
    parser = argparse.ArgumentParser(description="對黃金題庫跑檢索評估，輸出 hit@1 / hit@3 等指標")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH, help="題庫 YAML 路徑")
    parser.add_argument(
        "--skip-generation", action="store_true", help="只量檢索層指標，不呼叫 LLM（不想燒額度時用）"
    )
    parser.add_argument("--limit", type=int, help="只跑前 N 題，用於快速煙霧測試")
    parser.add_argument("--category", type=str, help="只跑指定 category 的題目（例如 policy、personal）")
    parser.add_argument("--save-answers", type=Path, help="把每題的問題、期望要點、實際回答寫成文字檔")
    args = parser.parse_args()

    passed = asyncio.run(_main_async(args))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
