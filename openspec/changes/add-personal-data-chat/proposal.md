# Proposal：AI 助理的個人資料查詢（批 B）

## Why

批 A 的 AI 助理完全唯讀、只答政策文件，畫面上還留著一行免責：「個人出勤紀錄、假別剩餘量
與申請進度請至對應功能頁查詢」。實際試用下來，使用者真正想問的多半是結合了政策與自身
狀況的問題——「我八月遲到幾次」、「我特休還剩幾天」、「我有幾張申請卡在那裡」。這些問題
語料裡永遠不會有答案，因為答案在資料庫裡。

批 A 刻意把這塊留給批 B，理由寫在 `openspec/changes/add-policy-chat/design.md`
「為批 B 鋪路」：個人資料牽涉授權邊界，風險等級與唯讀語料問答完全不同，值得單獨設計與
測試。批 A 已經預留好擴充點（`chat.ask()` 收整包 `current_user`、`answer.kind` 分流、
`generate()` 的 `tools` 參數位、`rate_limit.check_and_record()` 通用介面）。

**核心原則（使用者定調）**：AI 查得到的資料範圍，等於該角色在前端看得到的範圍。達成方式
不是在提示詞裡叮嚀模型守規矩，而是**讓工具呼叫與前端走同一支 service 函式、同一套範圍
限縮**。權限矩陣改了，兩邊同時跟著改，不可能不一致。

前置條件已完成：`fix-manager-attendance-scope` 修好了「主管匯得出部門出勤卻看不到」的
不一致，並把可見範圍解析抽成 `services/attendance_scope.py`，批 B 的工具直接沿用。

對應章節：`SPEC.md` §3.1（權限矩陣）、§3.2（範圍限縮）、§4.2（出勤生效值）、§4.12（AI 助理）、
§6.8；`docs/UI-SPEC.md` §3.18；`docs/PITFALLS.md` C1（權限判斷不得有第二套實作）、
I7～I12（批 A 的對話品質與延遲踩坑）。

## What Changes

- `GeminiClient.generate()` 實際支援 function calling（批 A 預留的 `tools` 參數），
  並新增一支處理工具往返的 `generate_with_tools()`。
- 新增 `services/chat_tools.py`：工具宣告、依角色組裝清單、派工到既有 service、
  結果聚合。**每一支工具都包既有 service，不新寫任何 SQL。**
- `chat.ask()` 在既有的政策路徑上加掛工具清單；模型不呼叫工具時行為與批 A 完全相同。
- `answer.kind` 新增 `"personal"`。
- 系統提示新增工具使用規則常數，與批 A 既有規則組合，不編輯已被 77 題驗證過的字串。
- eval 新增 `category: personal` 題組與**權限題組**（同一句話用三種角色問，驗證範圍差異）。
- 前端移除 ChatPage 的那行免責文案（批 A 埋的伏筆），空狀態建議問題加入個人類範例。

**不做**（見 `design.md`「非目標」）：任何寫入動作、薪資查詢、通訊錄查詢、場地借用查詢、
多輪對話記憶。

## Impact

新增：

- `backend/app/services/chat_tools.py`
- `backend/tests/test_chat_tools.py`
- `backend/tests/test_chat_tools_permission.py`

修改：

- `backend/app/utils/gemini.py`（`generate_with_tools()`）
- `backend/app/services/chat.py`（工具往返迴圈、`kind="personal"`）
- `backend/app/services/chat_prompt.py`（工具規則常數、注入虛擬時鐘的今天）
- `backend/app/config/settings.py`（工具往返的整體逾時與次數上限）
- `backend/tests/test_chat.py`、`backend/tests/helpers_chat.py`
- `backend/eval/questions.yaml`、`backend/eval/run_eval.py`
- `frontend/src/pages/ChatPage.jsx`、`frontend/src/pages/ChatPage.test.jsx`
- `e2e/chat.spec.js`
- `SPEC.md` §4.12／§6.8；`docs/UI-SPEC.md` §3.18；`docs/PITFALLS.md`；`.env.example`
