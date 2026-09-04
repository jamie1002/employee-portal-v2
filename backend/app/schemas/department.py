"""部門的手刻請求驗證（SPEC.md §4.7）。"""

from app.schemas.common import parse_optional_positive_int, require_str


def parse_department_body(data: dict) -> dict:
    name = require_str(data, "name", "請輸入部門名稱")
    manager_id = parse_optional_positive_int(data.get("manager_id"), "manager_id 格式不正確")
    return {"name": name, "manager_id": manager_id}
