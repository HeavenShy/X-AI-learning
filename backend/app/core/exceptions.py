import logging
from enum import IntEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ErrorCode(IntEnum):
    INVALID_PARAMS = 4000
    QUIZ_GENERATE_FAILED = 4001
    INPUT_TOO_SHORT = 4002
    CONTENT_NOT_ALLOWED = 4003
    REPORT_GENERATE_FAILED = 4004
    INTERNAL_ERROR = 5000


class BizError(Exception):
    """业务异常，统一映射为 {code, message, data: null}。"""

    def __init__(self, code: int, message: str, http_status: int = 200):
        super().__init__(message)
        self.code = int(code)
        self.message = message
        self.http_status = http_status


def _envelope(code: int, message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message, "data": None})


def _first_validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "请求参数不合法"
    err = errors[0]
    field = ".".join(str(p) for p in err.get("loc", []) if p != "body")
    return f"请求参数不合法：{field} {err.get('msg', '')}".strip()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def _biz_error_handler(_: Request, exc: BizError) -> JSONResponse:
        return _envelope(exc.code, exc.message, exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(ErrorCode.INVALID_PARAMS, _first_validation_message(exc), 422)

    @app.exception_handler(Exception)
    async def _unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return _envelope(ErrorCode.INTERNAL_ERROR, "服务开小差了，请稍后重试", 500)
