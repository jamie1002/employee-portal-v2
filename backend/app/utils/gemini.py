"""Gemini SDK 的唯一封裝。app 內其他地方（services／repositories／routers）
一律呼叫這裡的 `GeminiClient`，不得直接 import `google.generativeai`。

見 `openspec/changes/add-policy-chat/design.md` Decision 1：探針結果 `google-genai`
未通過 Gate 1（`Requires-Dist: pydantic<3.0.0,>=2.12.5`，會把 v2 鎖定的
`pydantic==2.10.4` 往上推），實際採用官方已停止維護但版本相容的
`google-generativeai==0.8.6`。import 這個套件時會印出一句 `FutureWarning`，
是套件本身的棄用警告，不是本專案的程式錯誤（見 `docs/PITFALLS.md`）。批 B 或未來
升級，必須等 `google-genai` 放寬 `pydantic` 下限、或 v2 的鎖定版本本身升級之後
再重跑探針。

**兩個容易搞混的「不對稱」**：
1. **正規化必須兩側一致**——這裡 document 與 query 兩側都做 L2 正規化。Gemini
   截斷維度後的向量預設沒有正規化（768 維時 L2 約 0.59）。
2. **`task_type` 則是刻意不對稱**——文件端用 `retrieval_document`、查詢端用
   `retrieval_query`，這是 Google 官方建議的檢索用法。這與第 1 點的正規化不同，
   不是不一致的錯誤。
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Any

import google.generativeai as genai

from app.config.settings import app_settings

_TASK_TYPE_DOCUMENT = "retrieval_document"
_TASK_TYPE_QUERY = "retrieval_query"

_throttle_lock = asyncio.Lock()
_last_call_at: dict[str, float] = {}


@dataclass
class ToolCall:
    """模型要求呼叫的工具。`name` 未經驗證——模型有可能喊出一個不存在、或它這個角色
    不該擁有的工具名稱，驗證是 service 層的責任（見 design.md Decision 2）。"""

    name: str
    args: dict


@dataclass
class ToolTurn:
    """帶工具那一輪的結果：要嘛模型要求呼叫工具，要嘛直接給了文字。

    `raw_content` 與 `user_content` 是把工具結果送回模型時要重建對話歷史用的，
    呼叫端不需要理解它們的內容。
    """

    calls: list[ToolCall]
    text: str
    raw_content: Any
    user_content: str


def _to_tool_turn(response: Any, user_content: str) -> ToolTurn:
    parts = response.candidates[0].content.parts
    calls = [
        ToolCall(name=part.function_call.name, args={k: v for k, v in part.function_call.args.items()})
        for part in parts
        if part.function_call and part.function_call.name
    ]
    # 有工具呼叫時 response.text 會拋例外（SDK 不允許對非純文字回應取 text），
    # 所以只在沒有呼叫時才取文字。
    text = "".join(part.text for part in parts if part.text) if not calls else ""
    return ToolTurn(calls=calls, text=text, raw_content=response.candidates[0].content, user_content=user_content)


class GeminiUnavailable(RuntimeError):
    """Gemini 呼叫在功能上不可用：未設定金鑰、逾時、維度不符、或任何上游例外。

    刻意是 `RuntimeError` 而非 `AppError`——呼叫端（router 的 `get_chat_client`
    dependency、`services/chat.py` 的 `ask()`）必須自己攔截並轉譯成
    `AppError(503, ..., "CHAT_UNAVAILABLE")`，否則會被 unhandled exception handler
    吃成未分類的 500。
    """


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _check_dimension(vector: list[float]) -> None:
    if len(vector) != app_settings.EMBEDDING_DIM:
        raise GeminiUnavailable(
            f"embedding 維度不符：模型實際輸出 {len(vector)} 維，"
            f"但 EMBEDDING_DIM 設定為 {app_settings.EMBEDDING_DIM} 維。換過模型或維度時，"
            "記得同步修改 .env 的 EMBEDDING_DIM、migration 的 vector(N)，並清空重灌整張表。"
        )


async def _throttle(key: str) -> None:
    """行程級 RPM 節流：確保同一種呼叫類型的間隔至少 60 / GEMINI_REQUESTS_PER_MINUTE 秒。

    免費層每分鐘請求數有上限，主動放慢呼叫節奏，寧可慢一點也不要撞 429 後在使用者的
    請求路徑上長時間重試。

    **`key` 依呼叫類型（`"embedding"` / `"generate"`）各自獨立計時**：embedding 與
    生成呼叫的是 Gemini 不同的模型端點，各自有獨立的配額桶，共用同一個全域計時器
    會讓單次問答內部「先 embed 再 generate」這兩次呼叫互相排隊——使用者會被迫多等
    一個節流間隔，卻誤以為是模型在思考（見 `docs/PITFALLS.md`）。

    等待動作刻意放在鎖外執行，鎖只保護「查詢並登記下一個時間槽」這個極短的臨界區，
    避免某一種呼叫的等待時間把其他呼叫（含不同 key、或並行的其他使用者請求）一併
    卡住。"""
    rpm = app_settings.GEMINI_REQUESTS_PER_MINUTE
    if rpm <= 0:
        return
    min_interval = 60.0 / rpm
    async with _throttle_lock:
        now = time.monotonic()
        last = _last_call_at.get(key, 0.0)
        wait = max(0.0, last + min_interval - now)
        _last_call_at[key] = now + wait
    if wait > 0:
        await asyncio.sleep(wait)


class GeminiClient:
    """單次請求可重用的 Gemini client。`generate()` 的 `tools` 參數是為批 B 的
    function calling 預留的位子，批 A 恆傳 `None`。

    **`throttled` 預設 True，但互動式問答（`/api/chat`）刻意傳 False**：節流是
    為了保護免費層配額，代價是每次呼叫之間強制等待 `60 / RPM` 秒。這個代價對
    「連續跑 72 題的 eval」或「一次灌 61 個 chunk 的 ingest」是划算的（慢一點
    無所謂），但對真人互動式問答是純粹的體驗傷害——使用者每問一題就被迫多等
    數秒，卻不知道系統在等什麼。互動路徑的配額保護改由
    `CHAT_RATE_LIMIT_PER_MINUTE`（每使用者每分鐘上限，超過直接回 429）負責：
    明確拒絕比默默拖延誠實得多（見 `docs/PITFALLS.md` I8）。
    """

    def __init__(self, throttled: bool = True) -> None:
        genai.configure(api_key=app_settings.GOOGLE_API_KEY)
        self._throttled = throttled

    async def _maybe_throttle(self, key: str) -> None:
        if self._throttled:
            await _throttle(key)

    async def _with_timeout(self, coro: Any) -> Any:
        try:
            return await asyncio.wait_for(coro, timeout=app_settings.GEMINI_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise GeminiUnavailable("呼叫 Gemini API 逾時。") from exc
        except GeminiUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — 上游 SDK 例外一律視為服務不可用
            raise GeminiUnavailable(f"呼叫 Gemini API 失敗：{exc}") from exc

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """把一批文件片段轉成向量列表，順序與輸入的 texts 一一對應（一次批次呼叫）。"""
        if not texts:
            return []

        async def _call() -> list[list[float]]:
            await self._maybe_throttle("embedding")
            response = await genai.embed_content_async(
                model=app_settings.EMBEDDING_MODEL,
                content=texts,
                task_type=_TASK_TYPE_DOCUMENT,
                output_dimensionality=app_settings.EMBEDDING_DIM,
            )
            return [_normalize(vector) for vector in response["embedding"]]

        vectors = await self._with_timeout(_call())
        for vector in vectors:
            _check_dimension(vector)
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """把使用者的查詢文字轉成向量。task_type 刻意與 embed_documents 不同。"""

        async def _call() -> list[float]:
            await self._maybe_throttle("embedding")
            response = await genai.embed_content_async(
                model=app_settings.EMBEDDING_MODEL,
                content=text,
                task_type=_TASK_TYPE_QUERY,
                output_dimensionality=app_settings.EMBEDDING_DIM,
            )
            return _normalize(response["embedding"])

        vector = await self._with_timeout(_call())
        _check_dimension(vector)
        return vector

    async def generate(self, system_instruction: str, user_content: str, tools: Any = None) -> str:
        """呼叫生成模型。

        `temperature` 走 `GEMINI_TEMPERATURE` 設定值。**這個值與「回答語氣溫暖與否」
        沒有直接關係**（那是系統提示措辭決定的），它影響的是用詞的隨機性；調高有機會
        讓措辭略微自然，但也會讓輸出更不穩定——規則 2（數字必須有依據）這類需要精確
        遵守的約束，temperature 越高越容易被模型「順口」帶過。任何調整都必須重跑
        `npm run eval:chat` 確認六項門檻仍然全綠，不能只憑讀起來的感覺。"""

        async def _call() -> str:
            await self._maybe_throttle("generate")
            model = genai.GenerativeModel(
                model_name=app_settings.GEMINI_MODEL,
                system_instruction=system_instruction,
            )
            response = await model.generate_content_async(
                user_content,
                generation_config=genai.types.GenerationConfig(
                    temperature=app_settings.GEMINI_TEMPERATURE
                ),
            )
            return response.text

        return await self._with_timeout(_call())

    async def generate_with_tools(
        self, system_instruction: str, user_content: str, tools: list[Any]
    ) -> ToolTurn:
        """帶著工具清單呼叫模型，回傳「要呼叫哪些工具」或「最終文字」。

        **這一層刻意不決定要不要執行工具，也不執行它們**——工具的權限判斷與派工屬於
        service 層（`services/chat_tools.py`）。SDK 封裝若順手把工具執行掉，授權敏感的
        控制流就藏進了這支通用工具函式裡，之後沒有人會想到要來這裡檢查權限。
        """

        async def _call() -> ToolTurn:
            await self._maybe_throttle("generate")
            model = genai.GenerativeModel(
                model_name=app_settings.GEMINI_MODEL,
                system_instruction=system_instruction,
                tools=tools,
            )
            response = await model.generate_content_async(
                user_content,
                generation_config=genai.types.GenerationConfig(
                    temperature=app_settings.GEMINI_TEMPERATURE
                ),
            )
            return _to_tool_turn(response, user_content)

        return await self._with_timeout(_call())

    async def continue_with_tool_results(
        self,
        system_instruction: str,
        tools: list[Any],
        turn: ToolTurn,
        results: list[tuple[str, dict]],
    ) -> str:
        """把工具執行結果送回模型，取得最終的文字回答。

        `results` 的順序必須與 `turn.calls` 一一對應。

        **這一輪以 `function_calling_config.mode = NONE` 禁止模型再呼叫工具。** 工具清單
        仍然要帶（歷史紀錄裡有 function_call，不宣告工具 API 會拒絕），但不加這個設定時
        模型偶爾會在第二輪再要一次工具——09-13 實測「我主管的分機?」，模型查完部門
        名單後又想查一次姓名，`response.text` 當場拋出「Could not convert
        part.function_call to text」，使用者看到 503。「工具往返只有一輪」
        （design.md Decision 6）必須由 API 保證，不能靠模型自律。
        """

        async def _call() -> str:
            await self._maybe_throttle("generate")
            model = genai.GenerativeModel(
                model_name=app_settings.GEMINI_MODEL,
                system_instruction=system_instruction,
                tools=tools,
            )
            history = [
                {"role": "user", "parts": [turn.user_content]},
                turn.raw_content,
                {
                    "role": "user",
                    "parts": [
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=name, response={"result": payload}
                            )
                        )
                        for name, payload in results
                    ],
                },
            ]
            # 禁止呼叫工具之後，lite 模型偶爾仍會回一個沒有任何文字的空回應（09-13 實測
            # 同一題 3 次出現 1 次，直接重打 4 次全部正常）。只重試一次：這是偶發的上游
            # 行為，不是提示詞問題，無限重試只會把配額燒掉。
            finish_reason = None
            for _ in range(2):
                response = await model.generate_content_async(
                    history,
                    generation_config=genai.types.GenerationConfig(
                        temperature=app_settings.GEMINI_TEMPERATURE
                    ),
                    tool_config={"function_calling_config": {"mode": "NONE"}},
                )
                # 不用 `response.text`：回應裡只要混了任何非文字的 part 它就拋例外。
                candidate = response.candidates[0] if response.candidates else None
                parts = candidate.content.parts if candidate else []
                text = "".join(part.text for part in parts if part.text)
                if text:
                    return text
                finish_reason = candidate.finish_reason if candidate else None
            raise GeminiUnavailable(f"第二輪沒有產生任何文字回答（finish_reason={finish_reason}）。")

        return await self._with_timeout(_call())


def get_gemini_client(throttled: bool = True) -> GeminiClient:
    """惰性建構 client。沒有設定金鑰時直接拋 GeminiUnavailable，呼叫端負責轉譯。

    `throttled=False` 供互動式問答路徑使用（見 `GeminiClient` 的說明）；
    ingest 與 eval 這類批次作業維持預設的節流。"""
    if not app_settings.chat_enabled:
        raise GeminiUnavailable("尚未設定 GOOGLE_API_KEY，AI 助理目前無法使用。")
    return GeminiClient(throttled=throttled)
