"""手刻請求驗證。v2 慣例不用 pydantic model 做請求驗證，見 `app/schemas/common.py`。"""

from app.config.settings import app_settings
from app.schemas.common import require_str, validation_error


def parse_chat_request(data: dict) -> dict:
    question = require_str(data, "question", "question 為必填")
    if len(question) > app_settings.CHAT_MAX_QUESTION_CHARS:
        raise validation_error(f"question 不得超過 {app_settings.CHAT_MAX_QUESTION_CHARS} 字")
    return {"question": question}
