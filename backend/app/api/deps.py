"""依赖注入：路由通过 Depends 获取服务，测试里用 dependency_overrides 替换为假模型。"""

from functools import lru_cache

from app.core.config import get_settings
from app.llm.langchain_factory import create_chat_model
from app.llm.quiz_chain import LangChainQuizGenerator
from app.llm.report_chain import LangChainReportGenerator
from app.services.quiz_service import QuizService
from app.services.report_service import ReportService
from app.utils.content_filter import get_content_filter


@lru_cache
def get_quiz_service() -> QuizService:
    s = get_settings()
    llm = create_chat_model(temperature=s.quiz_temperature, max_tokens=s.quiz_max_tokens, settings=s)
    return QuizService(LangChainQuizGenerator(llm), settings=s, content_filter=get_content_filter())


@lru_cache
def get_report_service() -> ReportService:
    s = get_settings()
    llm = create_chat_model(temperature=s.report_temperature, max_tokens=s.report_max_tokens, settings=s)
    return ReportService(LangChainReportGenerator(llm), settings=s, content_filter=get_content_filter())
