"""應用層例外類別。所有預期內的業務錯誤一律拋出 AppError，
交由 middleware/error_handler.py 轉譯為統一格式，不得讓例外直接外洩成未分類的 500。
"""


class AppError(Exception):
    def __init__(self, status_code: int, message: str, code: str):
        self.status_code = status_code
        self.message = message
        self.code = code
        super().__init__(message)
