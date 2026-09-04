"""業務資料表清單，供種子資料載入（TRUNCATE）與 admin 的資料庫檢視頁共用。

順序依外鍵相依，子表在前、父表在後——雖然 `RESTART IDENTITY CASCADE` 本身就會處理
相依關係，但清單也用來驅動畫面顯示順序，獨立維護比每次重新推導可靠。
"""

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
