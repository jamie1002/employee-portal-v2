"""統一錯誤處理：AppError 與 PostgreSQL 例外一律轉譯為 {"error": {"message", "code"}} 格式。

任何預期內的資料庫衝突都不得外洩成未經轉譯的 500（見 SPEC.md §7.1）。
"""

import structlog
from asyncpg.exceptions import (
    ExclusionViolationError,
    ForeignKeyViolationError,
    UniqueViolationError,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.utils.errors import AppError

logger = structlog.get_logger()


def _error_response(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"message": message, "code": code}})


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.message, exc.code)


async def unique_violation_handler(request: Request, exc: UniqueViolationError) -> JSONResponse:
    return _error_response(409, "資料已存在，違反唯一性限制。", "23505")


async def exclusion_violation_handler(request: Request, exc: ExclusionViolationError) -> JSONResponse:
    return _error_response(409, "此操作與既有資料衝突。", "23P01")


async def foreign_key_violation_handler(request: Request, exc: ForeignKeyViolationError) -> JSONResponse:
    return _error_response(400, "關聯的資料不存在或不合法。", "23503")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc)
    return _error_response(500, "伺服器發生未預期的錯誤，請稍後再試。", "INTERNAL_ERROR")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(UniqueViolationError, unique_violation_handler)
    app.add_exception_handler(ExclusionViolationError, exclusion_violation_handler)
    app.add_exception_handler(ForeignKeyViolationError, foreign_key_violation_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
