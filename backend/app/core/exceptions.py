from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class BizError(Exception):
    """业务异常，统一映射为 {code, message, data: null}。"""

    def __init__(self, code: int, message: str, http_status: int = 200):
        self.code = code
        self.message = message
        self.http_status = http_status


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def _biz_error_handler(_: Request, exc: BizError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "data": None},
        )
