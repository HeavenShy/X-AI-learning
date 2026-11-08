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
from app.rag.embedding import SiliconFlowEmbedder
from app.rag.vector_store import ChromaVectorStore
from app.repositories import kb_repository
from app.services.kb_ingest import KbIngestor
from app.services.bilibili import BilibiliClient
from app.services.transcriber import SiliconFlowTranscriber
from app.services.video_jobs import VideoJobManager
from app.services.web_page import LocalPageFetcher, PageReader, TavilyExtractor
from app.services.web_search import TavilySearcher
from app.utils.content_filter import get_content_filter
from app.services.wechat_auth import MockWeChatAuth, WeChatAuth

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
# Windows 等环境的 mimetypes 不一定认识字体后缀；content-type 不对时 wx.loadFontFace 会解析失败
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/ttf", ".ttf")


async def _recover_documents(db: Database) -> None:
    """上次进程退出时还在处理中的资料标为失败（处理任务在进程内，重启即中断）。"""
    try:
        async with db.transaction() as cur:
            n = await kb_repository.fail_interrupted(cur)
    except Exception:  # noqa: BLE001 —— 恢复失败不影响启动
        logger.exception("recover processing documents failed")
        return
    if n:
        logger.warning("%d 份处理中的资料因进程重启被标为失败", n)


def _clear_upload_dir(path: Path) -> None:
    if not path.is_dir():
        return
    for f in path.iterdir():
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                logger.warning("remove stale upload %s failed", f.name)


def _start_kb(app: FastAPI, settings: Settings) -> list:
    """创建知识库组件（测试可预先在 app.state 放假实现）。返回需要在关闭时释放的对象。"""
    state = app.state
    owned: list = []
    if state.db is None:
        logger.warning("数据库不可用，知识库功能关闭")
        return owned
    if not settings.kb_enabled:
        logger.info("未配置 SILICONFLOW_API_KEY，知识库功能关闭")
        return owned
    try:
        if state.embedder is None:
            state.embedder = SiliconFlowEmbedder(settings)
            owned.append(state.embedder)
        if state.vector_store is None:
            Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
            state.vector_store = ChromaVectorStore(settings.chroma_path, model=settings.embedding_model)
            owned.append(state.vector_store)
        state.kb_ingestor = KbIngestor(
            state.db,
            settings=settings,
            embedder=state.embedder,
            vector_store=state.vector_store,
            content_filter=state.content_filter or get_content_filter(),
        )
    except Exception:  # noqa: BLE001 —— 向量库打不开时其余功能照常，知识库接口返回 5000
        logger.exception("知识库初始化失败，知识库功能关闭")
        state.kb_ingestor = None
        state.vector_store = None
        return owned
    logger.info("知识库已开启（%s，向量库 %s）", settings.embedding_model, settings.chroma_path)
    return owned


async def _close_kb(app: FastAPI, owned: list) -> None:
    if app.state.kb_ingestor is not None:
        await app.state.kb_ingestor.aclose()
    for obj in owned:
        try:
            if hasattr(obj, "aclose"):
                await obj.aclose()
            elif hasattr(obj, "close"):
                obj.close()
        except Exception:  # noqa: BLE001
            logger.exception("close %s failed", type(obj).__name__)


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

    # 网页出题的抓取器（测试可预先在 app.state 放假实现）
    web_owned = False
    if app.state.page_reader is None and settings.web_fetch_enabled:
        use_tavily = settings.web_search_enabled and settings.web_extract_tavily_fallback
        app.state.page_reader = PageReader(
            settings,
            fetcher=LocalPageFetcher(settings),
            extractor=TavilyExtractor(settings) if use_tavily else None,
        )
        web_owned = True
        logger.info("网页出题已开启（本地抓取%s）", "，Tavily Extract 兜底" if use_tavily else "")

    # 视频出题的解析任务（测试可预先在 app.state 放假实现）
    video_owned = False
    if app.state.video_jobs is None and settings.video_available:
        app.state.video_jobs = VideoJobManager(
            settings,
            transcriber=SiliconFlowTranscriber(settings),
            bilibili=BilibiliClient(settings) if settings.bilibili_enabled else None,
            content_filter=app.state.content_filter or get_content_filter(),
        )
        app.state.video_jobs.clear_tmp()
        video_owned = True
        logger.info("视频出题已开启（%s%s）", settings.asr_model, "，支持 B 站链接" if settings.bilibili_enabled else "")
    elif not settings.video_available:
        logger.info("视频出题关闭（VIDEO_ENABLED=false 或未配置 SILICONFLOW_API_KEY）")

    if app.state.db is not None:
        await _recover_documents(app.state.db)
    _clear_upload_dir(Path(settings.kb_upload_dir))
    kb_owned = _start_kb(app, settings)
    try:
        yield
    finally:
        await _close_kb(app, kb_owned)
        if video_owned:
            await app.state.video_jobs.aclose()
            app.state.video_jobs = None
        if web_owned:
            await app.state.page_reader.aclose()
            app.state.page_reader = None
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
    app.state.page_reader = None
    app.state.video_jobs = None
    # 知识库组件：lifespan 里创建；测试可在启动前放入假实现（embedder / vector_store / content_filter）
    app.state.embedder = None
    app.state.vector_store = None
    app.state.kb_ingestor = None
    app.state.content_filter = None
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
