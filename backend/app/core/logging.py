import logging
import time

from fastapi import FastAPI, Request

_configured = False


def setup_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    # 第三方库日志太吵
    for noisy in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def register_request_logging(app: FastAPI) -> None:
    logger = logging.getLogger("app.access")

    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        cost_ms = (time.perf_counter() - start) * 1000
        logger.info("%s %s -> %s %.0fms", request.method, request.url.path, response.status_code, cost_ms)
        return response
