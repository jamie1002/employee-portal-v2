"""測試共用小工具。

種子資料的固定事實（見 db/seed/001_seed.sql）：
- 使用者 1 系統管理者(admin, 無部門)、2 王小明(manager, 研發部)、3 陳小華(employee, 研發部)、
  4 林小美(manager, 業務部)、5 張大同(employee, 業務部)、6 李小芳(employee, 人資部)
- 所有帳號密碼一律 Demo1234
- 虛擬時鐘錨在 2026-08-24 09:00（週一），可調範圍 2026-08-24 ~ 08-31
- 考勤設定 09:00–18:00、午休 12:00–13:00、緩衝 10 分
"""

from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")

DEMO_PASSWORD = "Demo1234"

ADMIN_ID, MANAGER_ID, EMPLOYEE_ID = 1, 2, 3
OTHER_MANAGER_ID, OTHER_EMPLOYEE_ID = 4, 5


def taipei(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=TZ)


async def login(client, email: str, password: str = DEMO_PASSWORD) -> str:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def login_headers(client, email: str) -> dict:
    return auth(await login(client, email))
