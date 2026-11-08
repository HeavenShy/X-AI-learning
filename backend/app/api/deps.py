"""依赖注入：路由通过 Depends 获取服务，测试里用 dependency_overrides 替换为假模型。"""

from functools import lru_cache

from fastapi import Depends, Request
from langchain_openai import ChatOpenAI

from app.agent.retrieval_planner import RetrievalPlanner
from app.core.auth import optional_user_id
from app.core.config import get_settings
from app.core.db import Database
from app.core.exceptions import BizError, ErrorCode
from app.llm.insight_chain import InsightGenerator, LangChainInsightGenerator
from app.llm.kb_quiz_chain import KbQuizGenerator, LangChainKbQuizGenerator
from app.llm.langchain_factory import create_chat_model
from app.llm.quiz_chain import LangChainQuizGenerator, QuizGenerator
from app.llm.report_chain import LangChainReportGenerator
from app.llm.web_quiz_chain import LangChainWebQuizGenerator, WebQuizGenerator
from app.llm.web_scope_chain import LangChainWebScopeJudge, WebScopeJudge
from app.rag.vector_store import VectorStore
from app.services.history_service import HistoryService
from app.services.kb_ingest import KbIngestor
from app.services.kb_quiz_service import KbQuizService
from app.services.kb_retrieval import KbRetriever
from app.services.kb_service import KbService
from app.services.quiz_service import QuizService
from app.services.report_service import ReportService
from app.services.review_service import ReviewService
from app.services.stats_service import StatsService
from app.services.user_service import UserService
from app.services.video_jobs import VideoJobManager
from app.services.video_quiz_service import VideoQuizService
from app.services.web_quiz_service import WebQuizService
from app.services.wechat_auth import WeChatAuthClient
from app.utils.content_filter import ContentFilter, get_content_filter

MSG_DB_UNAVAILABLE = "用户系统暂时不可用，请稍后重试"
MSG_KB_UNAVAILABLE = "知识库功能暂时不可用，请稍后重试"
MSG_WEB_UNAVAILABLE = "网页出题暂时不可用，请稍后重试"
MSG_VIDEO_UNAVAILABLE = "视频出题暂时不可用，请稍后重试"
# 学习结论只要一两句话
INSIGHT_MAX_TOKENS = 400


@lru_cache
def get_quiz_generator() -> LangChainQuizGenerator:
    """LLM 客户端是进程级单例。"""
    s = get_settings()
    llm = create_chat_model(temperature=s.quiz_temperature, max_tokens=s.quiz_max_tokens, settings=s)
    return LangChainQuizGenerator(llm)


@lru_cache
def get_retrieval_llm() -> ChatOpenAI:
    """检索规划用的模型：低温度、小 max_tokens，进程级单例。"""
    s = get_settings()
    return create_chat_model(temperature=s.agent_temperature, max_tokens=s.agent_max_tokens, settings=s)


def get_retrieval_planner(
    request: Request,
    content_filter: ContentFilter = Depends(get_content_filter),
    llm: ChatOpenAI = Depends(get_retrieval_llm),
) -> RetrievalPlanner | None:
    """总开关关闭时为 None：两个入口都走固定规则。"""
    settings = request.app.state.settings
    if not settings.agent_retrieval_enabled:
        return None
    return RetrievalPlanner(llm, settings=settings, content_filter=content_filter)


def get_db(request: Request) -> Database | None:
    """没配库 / 连不上库时为 None：出题、报告照常工作，只是不落库。"""
    return getattr(request.app.state, "db", None)


def get_home_kb_retriever(
    request: Request,
    user_id: int | None = Depends(optional_user_id),
    db: Database | None = Depends(get_db),
) -> KbRetriever | None:
    """首页出题的知识库工具：只在已登录且知识库可用时组装，绑定当前用户（资料是否 ready 由服务层查）。"""
    kb = kb_runtime(request, db)
    if user_id is None or kb is None:
        return None
    return KbRetriever(
        kb.db,
        user_id=user_id,
        embedder=kb.embedder,
        vector_store=kb.vector_store,
        top_k=request.app.state.settings.agent_kb_top_k,
    )


def get_quiz_service(
    request: Request,
    generator: QuizGenerator = Depends(get_quiz_generator),
    content_filter: ContentFilter = Depends(get_content_filter),
    planner: RetrievalPlanner | None = Depends(get_retrieval_planner),
    kb_retriever: KbRetriever | None = Depends(get_home_kb_retriever),
) -> QuizService:
    """每请求组装：检索客户端由 lifespan 挂在 app.state（没配 Key 时为 None）。"""
    return QuizService(
        generator,
        settings=request.app.state.settings,
        content_filter=content_filter,
        searcher=getattr(request.app.state, "web_searcher", None),
        planner=planner,
        kb_retriever=kb_retriever,
    )


@lru_cache
def get_report_service() -> ReportService:
    s = get_settings()
    llm = create_chat_model(temperature=s.report_temperature, max_tokens=s.report_max_tokens, settings=s)
    return ReportService(LangChainReportGenerator(llm), settings=s, content_filter=get_content_filter())


def require_db(db: Database | None = Depends(get_db)) -> Database:
    if db is None:
        raise BizError(ErrorCode.INTERNAL_ERROR, MSG_DB_UNAVAILABLE, http_status=503)
    return db


def get_wechat_auth(request: Request) -> WeChatAuthClient:
    return request.app.state.wechat


def get_user_service(
    request: Request,
    db: Database = Depends(require_db),
    content_filter: ContentFilter = Depends(get_content_filter),
) -> UserService:
    return UserService(db, settings=request.app.state.settings, content_filter=content_filter)


def get_history_service(db: Database | None = Depends(get_db)) -> HistoryService | None:
    return HistoryService(db) if db is not None else None


def require_history_service(db: Database = Depends(require_db)) -> HistoryService:
    return HistoryService(db)


@lru_cache
def get_insight_generator() -> LangChainInsightGenerator:
    s = get_settings()
    llm = create_chat_model(temperature=s.report_temperature, max_tokens=INSIGHT_MAX_TOKENS, settings=s)
    return LangChainInsightGenerator(llm)


def require_stats_service(
    db: Database = Depends(require_db),
    generator: InsightGenerator = Depends(get_insight_generator),
    content_filter: ContentFilter = Depends(get_content_filter),
) -> StatsService:
    return StatsService(db, generator, content_filter=content_filter)


def require_review_service(db: Database = Depends(require_db)) -> ReviewService:
    return ReviewService(db)


# ---------- 知识库 ----------


class KbRuntime:
    """知识库需要的进程级组件（lifespan 创建，挂在 app.state）。"""

    def __init__(self, db: Database, vector_store: VectorStore, ingestor: KbIngestor, embedder):
        self.db = db
        self.vector_store = vector_store
        self.ingestor = ingestor
        self.embedder = embedder


def kb_runtime(request: Request, db: Database | None) -> KbRuntime | None:
    """知识库可用（有库、配了 Embedding Key、向量库与处理器已初始化）时返回运行时组件，否则 None。"""
    state = request.app.state
    if (
        db is None
        or not state.settings.kb_enabled
        or getattr(state, "vector_store", None) is None
        or getattr(state, "kb_ingestor", None) is None
        or getattr(state, "embedder", None) is None
    ):
        return None
    return KbRuntime(db, state.vector_store, state.kb_ingestor, state.embedder)


def require_kb(request: Request, db: Database | None = Depends(get_db)) -> KbRuntime:
    """没有库、没配 Embedding Key（或向量库初始化失败）时，知识库接口一律 5000 / 503。"""
    kb = kb_runtime(request, db)
    if kb is None:
        raise BizError(ErrorCode.INTERNAL_ERROR, MSG_KB_UNAVAILABLE, http_status=503)
    return kb


def require_kb_service(
    request: Request,
    kb: KbRuntime = Depends(require_kb),
    content_filter: ContentFilter = Depends(get_content_filter),
) -> KbService:
    return KbService(
        kb.db, settings=request.app.state.settings, content_filter=content_filter, vector_store=kb.vector_store
    )


@lru_cache
def get_kb_quiz_generator() -> LangChainKbQuizGenerator:
    """与文本出题相同的模型参数，进程级单例。"""
    s = get_settings()
    llm = create_chat_model(temperature=s.quiz_temperature, max_tokens=s.quiz_max_tokens, settings=s)
    return LangChainKbQuizGenerator(llm)


def require_kb_quiz_service(
    request: Request,
    kb: KbRuntime = Depends(require_kb),
    generator: KbQuizGenerator = Depends(get_kb_quiz_generator),
    content_filter: ContentFilter = Depends(get_content_filter),
    planner: RetrievalPlanner | None = Depends(get_retrieval_planner),
) -> KbQuizService:
    return KbQuizService(
        kb.db,
        generator,
        settings=request.app.state.settings,
        content_filter=content_filter,
        embedder=kb.embedder,
        vector_store=kb.vector_store,
        planner=planner,
        searcher=getattr(request.app.state, "web_searcher", None),
    )


# ---------- 网页出题 ----------


@lru_cache
def get_web_scope_judge() -> LangChainWebScopeJudge:
    """范围判断：低温度、小 max_tokens，进程级单例。"""
    s = get_settings()
    return LangChainWebScopeJudge(
        create_chat_model(temperature=s.agent_temperature, max_tokens=s.web_scope_max_tokens, settings=s)
    )


@lru_cache
def get_web_quiz_generator() -> LangChainWebQuizGenerator:
    """与文本出题相同的模型参数，进程级单例。"""
    s = get_settings()
    llm = create_chat_model(temperature=s.quiz_temperature, max_tokens=s.quiz_max_tokens, settings=s)
    return LangChainWebQuizGenerator(llm)


def require_web_quiz_service(
    request: Request,
    judge: WebScopeJudge = Depends(get_web_scope_judge),
    generator: WebQuizGenerator = Depends(get_web_quiz_generator),
    content_filter: ContentFilter = Depends(get_content_filter),
) -> WebQuizService:
    """网页抓取关闭（WEB_FETCH_ENABLED=false）时网页接口一律 5000 / 503。"""
    reader = getattr(request.app.state, "page_reader", None)
    if reader is None:
        raise BizError(ErrorCode.INTERNAL_ERROR, MSG_WEB_UNAVAILABLE, http_status=503)
    return WebQuizService(
        reader, judge, generator, settings=request.app.state.settings, content_filter=content_filter
    )


# ---------- 视频出题 ----------


def require_video_jobs(request: Request) -> VideoJobManager:
    """没配 SILICONFLOW_API_KEY 或 VIDEO_ENABLED=false 时视频接口一律 5000 / 503。"""
    jobs = getattr(request.app.state, "video_jobs", None)
    if jobs is None:
        raise BizError(ErrorCode.INTERNAL_ERROR, MSG_VIDEO_UNAVAILABLE, http_status=503)
    return jobs


def require_video_quiz_service(
    request: Request,
    jobs: VideoJobManager = Depends(require_video_jobs),
    judge: WebScopeJudge = Depends(get_web_scope_judge),
    generator: WebQuizGenerator = Depends(get_web_quiz_generator),
    content_filter: ContentFilter = Depends(get_content_filter),
) -> VideoQuizService:
    return VideoQuizService(jobs, judge, generator, settings=request.app.state.settings, content_filter=content_filter)
