import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import register_request_logging, setup_logging

STATIC_DIR = Path(__file__).resolve().parent / "static"
# Windows 等环境的 mimetypes 不一定认识字体后缀；content-type 不对时 wx.loadFontFace 会解析失败
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/ttf", ".ttf")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_request_logging(app)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    # 漫画标题字体（wx.loadFontFace 从这里加载）
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
