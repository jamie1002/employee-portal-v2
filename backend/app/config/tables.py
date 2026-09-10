"""業務資料表清單，供種子資料載入（TRUNCATE）與 admin 的資料庫檢視頁共用。

順序依外鍵相依，子表在前、父表在後——雖然 `RESTART IDENTITY CASCADE` 本身就會處理
相依關係，但清單也用來驅動畫面顯示順序，獨立維護比每次重新推導可靠。
"""

# policy_embeddings（AI 政策問答的語料向量表）刻意不列入這份清單：這裡會被種子
# 載入 TRUNCATE，且正式環境有 15 分鐘閒置自動重置，加進去會讓 AI 助理每 15 分鐘
# 失憶一次，且重建語料要重打數十次 embedding API（見
# openspec/changes/add-policy-chat/design.md Decision 4）。
BUSINESS_TABLES = [
    "room_bookings",
    "rooms",
    "holidays",
    "overtime_requests",
    "leave_requests",
    "punch_requests",
    "attendances",
    "user_permissions",
    "users",
    "departments",
    "system_settings",
    "demo_clock",
]
