"""依赖注入：路由通过 Depends 获取服务，测试里用 dependency_overrides 替换为假模型。"""

from functools import lru_cache

from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.db import Database
from app.core.exceptions import BizError, ErrorCode
from app.llm.langchain_factory import create_chat_model
from app.llm.quiz_chain import LangChainQuizGenerator, QuizGenerator
from app.llm.report_chain import LangChainReportGenerator
from app.services.history_service import HistoryService
from app.services.quiz_service import QuizService
from app.services.report_service import ReportService
from app.services.review_service import ReviewService
from app.services.user_service import UserService
from app.services.wechat_auth import WeChatAuthClient
from app.utils.content_filter import ContentFilter, get_content_filter

MSG_DB_UNAVAILABLE = "用户系统暂时不可用，请稍后重试"


@lru_cache
def get_quiz_generator() -> LangChainQuizGenerator:
    """LLM 客户端是进程级单例。"""
    s = get_settings()
    llm = create_chat_model(temperature=s.quiz_temperature, max_tokens=s.quiz_max_tokens, settings=s)
    return LangChainQuizGenerator(llm)


def get_quiz_service(
    request: Request,
    generator: QuizGenerator = Depends(get_quiz_generator),
    content_filter: ContentFilter = Depends(get_content_filter),
) -> QuizService:
    """每请求组装：检索客户端由 lifespan 挂在 app.state（没配 Key 时为 None，按原流程出题）。"""
    return QuizService(
        generator,
        settings=request.app.state.settings,
        content_filter=content_filter,
        searcher=getattr(request.app.state, "web_searcher", None),
    )


@lru_cache
def get_report_service() -> ReportService:
    s = get_settings()
    llm = create_chat_model(temperature=s.report_temperature, max_tokens=s.report_max_tokens, settings=s)
    return ReportService(LangChainReportGenerator(llm), settings=s, content_filter=get_content_filter())


def get_db(request: Request) -> Database | None:
    """没配库 / 连不上库时为 None：出题、报告照常工作，只是不落库。"""
    return getattr(request.app.state, "db", None)


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


def require_review_service(db: Database = Depends(require_db)) -> ReviewService:
    return ReviewService(db)
