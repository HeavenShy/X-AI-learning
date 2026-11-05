import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.db import Database, init_schema
from app.core.exceptions import register_exception_handlers
from app.core.logging import register_request_logging, setup_logging
from app.services.web_search import TavilySearcher
from app.services.wechat_auth import MockWeChatAuth, WeChatAuth

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
# Windows 等环境的 mimetypes 不一定认识字体后缀；content-type 不对时 wx.loadFontFace 会解析失败
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/ttf", ".ttf")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    if settings.db_enabled:
        try:
            app.state.db = await Database.connect(settings)
            if settings.mysql_auto_init:
                await init_schema(app.state.db)
        except Exception:  # noqa: BLE001 —— 连不上库时核心闯关仍可匿名使用，用户接口返回 5000
            logger.exception("MySQL 连接失败，用户系统不可用（出题 / 报告按匿名模式工作）")
            app.state.db = None
    else:
        logger.warning("未配置 MYSQL_DATABASE，用户系统不可用（出题 / 报告按匿名模式工作）")

    if settings.wechat_mock_login:
        logger.warning("WECHAT_APP_SECRET 未配置，开发环境使用模拟登录（所有设备登录同一个开发用户）")
        app.state.wechat = MockWeChatAuth()
    else:
        app.state.wechat = WeChatAuth(settings)

    if settings.web_search_enabled:
        app.state.web_searcher = TavilySearcher(settings)
        logger.info("出题前联网检索已开启（Tavily，%s）", settings.tavily_search_depth)
    else:
        app.state.web_searcher = None
        logger.info("未配置 TAVILY_API_KEY，出题不联网检索")
    try:
        yield
    finally:
        if app.state.web_searcher is not None:
            await app.state.web_searcher.aclose()
        await app.state.wechat.aclose()
        if app.state.db is not None:
            await app.state.db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = None
    app.state.wechat = None
    app.state.web_searcher = None
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
