"""出题服务：清洗 → 敏感词 → 取资料 → LangChain 出题 → 校验规范化 →（有资料时）出处 → 输出敏感词 → 失败换保守 Prompt 重试。

取资料（每次请求只做一次，重试复用）：
- 检索规划 Agent 开启且本次有可用数据源时，由 Agent 决定查知识库 / 联网 / 都查 / 都不查。
  可用数据源：配置了搜索 Key → 联网；已登录、知识库可用且有 ready 资料 → 该用户全部知识库。
  联网结果 → <reference>（事实依据）；知识库片段 → <materials>（按需引用，用到的题带出处）。
- Agent 关闭或规划失败：固定规则，以学习内容联网检索一次（尽力而为），不查知识库。

source_type：任一题带出处即为 knowledge_base，与历史详情的推导是同一个函数。
"""

import logging
import time

from app.agent.retrieval_planner import PlanContext, PlanningError, RetrievalPlanner, log_plan_skipped
from app.core.config import Settings
from app.core.exceptions import BizError, ErrorCode
from app.llm.quiz_chain import QuizGenerator
from app.models.quiz import Quiz, QuizContent, QuizGenerateRequest
from app.prompts.kb_quiz_prompt import MaterialPiece, format_materials
from app.prompts.quiz_prompt import CONSERVATIVE_QUIZ_PROMPT, DEFAULT_QUIZ_PROMPT
from app.services.history_service import source_type_of
from app.services.kb_materials import attach_sources, pieces_from_chunks, strip_sources
from app.services.kb_retrieval import KbRetriever
from app.services.quiz_retry import generate_with_retries
from app.services.quiz_validator import normalize_quiz
from app.services.web_search import SearchSnippet, WebSearcher, WebSearchError, build_reference
from app.utils.content_filter import ContentFilter
from app.utils.id_generator import new_quiz_id
from app.utils.text_cleaner import clean_text, visible_length

logger = logging.getLogger(__name__)

MSG_TOO_SHORT = "内容太短，AI 猜不出你想学哪方面。至少写 4 个字，比如“RAG 是怎么工作的”。"
MSG_NOT_ALLOWED = "这段内容涉及不适合出题的话题，换个主题试试。"
# 固定规则的检索查询词只取清洗后学习内容的前 N 个字：长文本作查询会降低相关度，也少发一些用户内容给第三方
SEARCH_QUERY_MAX_CHARS = 400


class QuizService:
    def __init__(
        self,
        generator: QuizGenerator,
        *,
        settings: Settings,
        content_filter: ContentFilter,
        searcher: WebSearcher | None = None,
        planner: RetrievalPlanner | None = None,
        kb_retriever: KbRetriever | None = None,
    ):
        self._generator = generator
        self._settings = settings
        self._filter = content_filter
        self._searcher = searcher
        self._planner = planner
        # 只在已登录且知识库可用时注入，绑定当前用户
        self._kb = kb_retriever

    def _check_input(self, req: QuizGenerateRequest) -> str:
        text = clean_text(req.user_input)
        if visible_length(text) < self._settings.input_min_chars:
            raise BizError(ErrorCode.INPUT_TOO_SHORT, MSG_TOO_SHORT)
        if self._filter.find(text):
            raise BizError(ErrorCode.CONTENT_NOT_ALLOWED, MSG_NOT_ALLOWED)
        return text

    def _build_reference(self, snippets: list[SearchSnippet]) -> str:
        return build_reference(
            snippets,
            item_max_chars=self._settings.web_reference_item_max_chars,
            total_max_chars=self._settings.web_reference_max_chars,
            content_filter=self._filter,
        )

    async def _reference(self, text: str) -> str:
        """固定规则：检索一次并整理为参考资料；没有 searcher 或任何失败都返回空串，不影响出题。"""
        if self._searcher is None:
            return ""
        start = time.perf_counter()
        try:
            snippets = await self._searcher.search(text[:SEARCH_QUERY_MAX_CHARS])
            reference = self._build_reference(snippets)
        except WebSearchError as exc:
            logger.warning(
                "web search failed (status=%s) after %.1fs, quiz continues without reference: %s",
                exc.status, time.perf_counter() - start, exc,
            )
            return ""
        except Exception as exc:  # noqa: BLE001 —— 检索是尽力而为，任何异常都降级
            logger.warning(
                "web search error after %.1fs, quiz continues without reference: %s",
                time.perf_counter() - start, type(exc).__name__,
            )
            return ""
        logger.info(
            "web search ok: %d results, reference %d chars, %.1fs",
            len(snippets), len(reference), time.perf_counter() - start,
        )
        return reference

    async def _kb_context(self) -> tuple[KbRetriever | None, list]:
        """首页的知识库工具：已登录、知识库可用且至少一份 ready 资料才可用。查库失败当作不可用。"""
        if self._kb is None:
            return None, []
        try:
            if not await self._kb.documents():
                return None, []
            return self._kb, await self._kb.catalog()
        except Exception as exc:  # noqa: BLE001 —— 知识库只是可选数据源
            logger.warning("list ready documents failed, plan without knowledge base: %s", type(exc).__name__)
            return None, []

    async def _gather(self, text: str) -> tuple[str, list[MaterialPiece]]:
        """取资料：返回 (参考资料文本, 知识库材料片段)。"""
        if self._planner is None or not self._settings.agent_retrieval_enabled:
            log_plan_skipped("home", "disabled")
            return await self._reference(text), []
        kb, catalog = await self._kb_context()
        if kb is None and self._searcher is None:
            log_plan_skipped("home", "no_tools")
            return "", []
        ctx = PlanContext(
            entry="home",
            text=text,
            kb_search=kb.search if kb is not None else None,
            web_search=self._searcher.search if self._searcher is not None else None,
            catalog=catalog,
        )
        try:
            result = await self._planner.plan(ctx)
        except PlanningError:
            return await self._reference(text), []
        reference = self._build_reference(result.web_snippets) if result.web_snippets else ""
        pieces = (
            pieces_from_chunks(result.kb_chunks, max_chars=self._settings.kb_material_max_chars)
            if result.kb_chunks
            else []
        )
        return reference, pieces

    async def generate(self, req: QuizGenerateRequest) -> Quiz:
        text = self._check_input(req)
        # 每次出题只取一次资料，换保守 Prompt 重试时复用
        reference, pieces = await self._gather(text)
        materials = format_materials(pieces) if pieces else ""

        async def attempt(version: str) -> QuizContent:
            kwargs = dict(
                user_input=text,
                question_count=req.question_count,
                difficulty=req.difficulty,
                prompt_version=version,
                reference=reference,
            )
            if materials:
                kwargs["materials"] = materials
            generated = await self._generator.generate(**kwargs)
            if not pieces:
                return normalize_quiz(generated, req.question_count)
            content = normalize_quiz(
                strip_sources(generated.title, generated.summary, generated.questions, topic=generated.topic), req.question_count
            )
            # 首页出题不要求每题都有出处：无效编号只丢弃
            return attach_sources(content, generated.questions, pieces, required=False)

        content = await generate_with_retries(
            attempt,
            attempts=self._settings.quiz_max_attempts,
            default_prompt=DEFAULT_QUIZ_PROMPT,
            conservative_prompt=CONSERVATIVE_QUIZ_PROMPT,
            content_filter=self._filter,
        )
        return Quiz(
            quiz_id=new_quiz_id(),
            user_input=text,
            source_type=source_type_of(content.questions),
            **content.model_dump(),
        )
