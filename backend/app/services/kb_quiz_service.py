"""知识库出题：确定资料范围 → 校验重点 → 取材料（+ 背景）→ 只依据资料出题 → 校验 + 出处 → 重试。

取材料（每次请求只做一次，重试复用）：
- 检索规划 Agent 开启时：填了重点 → Agent 可在所选 ready 资料里检索（自己改写 / 拆分查询词，片段去重合并），
  另可联网查背景（配置了搜索 Key 且 agent_web_in_kb_quiz 打开）；没填重点 → 只能决定是否联网查背景。
- Agent 的知识库片段为空（没查、没结果）、规划失败或 Agent 关闭：固定取材——有重点以重点向量检索一次，
  失败或没结果均匀抽取；没重点均匀抽取。规划失败或关闭时不联网。
- 联网结果只进 <background>：不作为出题依据，不进出处。每题仍必须有资料出处（required=True）。

结果结构与文本出题相同，source_type=knowledge_base，每题带 sources。
"""

import logging

from app.agent.retrieval_planner import KbChunk, PlanContext, PlanningError, RetrievalPlanner, log_plan_skipped
from app.core.config import Settings
from app.core.db import Database
from app.core.exceptions import BizError, ErrorCode
from app.llm.kb_quiz_chain import KbQuizGenerator
from app.models.kb import KbQuizRequest
from app.models.quiz import Quiz, QuizContent
from app.prompts.kb_quiz_prompt import CONSERVATIVE_KB_QUIZ_PROMPT, DEFAULT_KB_QUIZ_PROMPT, format_materials
from app.prompts.retrieval_agent_prompt import CatalogItem
from app.rag.embedding import Embedder
from app.rag.vector_store import VectorStore
from app.repositories import kb_repository as kbs
from app.services.kb_materials import attach_sources, pieces_from_chunks, select_materials, strip_sources
from app.services.kb_retrieval import KbRetriever
from app.services.kb_service import MSG_KB_NOT_FOUND
from app.services.quiz_retry import generate_with_retries
from app.services.quiz_validator import normalize_quiz
from app.services.web_search import WebSearcher, build_reference
from app.utils.content_filter import ContentFilter
from app.utils.id_generator import new_quiz_id
from app.utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)

MSG_DOC_NOT_IN_KB = "所选资料不在这个知识库里"
MSG_NO_READY_DOCUMENTS = "资料还没准备好：先上传资料，或等处理完成再出题"
MSG_FOCUS_NOT_ALLOWED = "重点内容涉及不适合出题的话题，换个说法试试。"


class KbQuizService:
    def __init__(
        self,
        db: Database,
        generator: KbQuizGenerator,
        *,
        settings: Settings,
        content_filter: ContentFilter,
        embedder: Embedder | None,
        vector_store: VectorStore | None,
        planner: RetrievalPlanner | None = None,
        searcher: WebSearcher | None = None,
    ):
        self._db = db
        self._generator = generator
        self._settings = settings
        self._filter = content_filter
        self._embedder = embedder
        self._vectors = vector_store
        self._planner = planner
        self._searcher = searcher

    def _check_focus(self, raw: str) -> str:
        focus = clean_text(raw)
        if focus and self._filter.find(focus):
            raise BizError(ErrorCode.CONTENT_NOT_ALLOWED, MSG_FOCUS_NOT_ALLOWED)
        return focus

    async def _ready_documents(self, user_id: int, kb_id: str, document_ids: list[str]) -> tuple[str, list[dict]]:
        """返回 (知识库名, 所选资料中 ready 的资料)。"""
        async with self._db.transaction() as cur:
            kb = await kbs.get_kb(cur, user_id, kb_id)
            if kb is None:
                raise BizError(ErrorCode.NOT_FOUND, MSG_KB_NOT_FOUND)
            docs = await kbs.list_documents(cur, user_id, kb_id)
        if document_ids:
            wanted = set(document_ids)
            if not wanted <= {d["document_id"] for d in docs}:
                raise BizError(ErrorCode.NOT_FOUND, MSG_DOC_NOT_IN_KB)
            docs = [d for d in docs if d["document_id"] in wanted]
        # 材料按上传先后排
        ready = sorted((d for d in docs if d["status"] == "ready"), key=lambda d: d["created_at"])
        if not ready:
            raise BizError(ErrorCode.NO_READY_DOCUMENTS, MSG_NO_READY_DOCUMENTS)
        return kb["name"], ready

    async def _plan(
        self, user_id: int, kb_name: str, documents: list[dict], focus: str
    ) -> tuple[list[KbChunk], str]:
        """检索规划：返回 (Agent 查到的片段, 背景资料文本)。关闭、没有可用工具或失败时都是 ([], "")。"""
        if self._planner is None or not self._settings.agent_retrieval_enabled:
            log_plan_skipped("kb", "disabled")
            return [], ""
        kb = None
        if focus and self._embedder is not None and self._vectors is not None:
            kb = KbRetriever(
                self._db,
                user_id=user_id,
                embedder=self._embedder,
                vector_store=self._vectors,
                top_k=self._settings.agent_kb_top_k,
                documents=documents,
            )
        web = self._searcher if self._settings.agent_web_in_kb_quiz else None
        if kb is None and web is None:
            log_plan_skipped("kb", "no_tools")
            return [], ""
        ctx = PlanContext(
            entry="kb",
            text=focus,
            kb_search=kb.search if kb is not None else None,
            web_search=web.search if web is not None else None,
            catalog=[CatalogItem(kb_name=kb_name, filename=d["filename"]) for d in documents],
        )
        try:
            result = await self._planner.plan(ctx)
        except PlanningError:
            # 退回固定规则：不联网，材料由固定取材得到
            return [], ""
        background = ""
        if result.web_snippets:
            background = build_reference(
                result.web_snippets,
                item_max_chars=self._settings.web_reference_item_max_chars,
                total_max_chars=self._settings.web_reference_max_chars,
                content_filter=self._filter,
                numbered=False,
            )
        return result.kb_chunks, background

    async def generate(self, user_id: int, kb_id: str, req: KbQuizRequest) -> Quiz:
        focus = self._check_focus(req.focus)
        kb_name, documents = await self._ready_documents(user_id, kb_id, req.document_ids)
        agent_chunks, background = await self._plan(user_id, kb_name, documents, focus)
        if agent_chunks:
            pieces = pieces_from_chunks(agent_chunks, max_chars=self._settings.kb_material_max_chars)
        else:
            pieces = await select_materials(
                self._db,
                user_id=user_id,
                documents=documents,
                focus=focus,
                embedder=self._embedder,
                vector_store=self._vectors,
                settings=self._settings,
            )
        if not pieces:
            # 资料的片段都命中了敏感词等情况
            raise BizError(ErrorCode.NO_READY_DOCUMENTS, MSG_NO_READY_DOCUMENTS)
        materials = format_materials(pieces)

        async def attempt(version: str) -> QuizContent:
            kwargs = dict(
                materials=materials,
                focus=focus,
                question_count=req.question_count,
                difficulty=req.difficulty,
                prompt_version=version,
            )
            if background:
                kwargs["background"] = background
            generated = await self._generator.generate(**kwargs)
            plain = strip_sources(generated.title, generated.summary, generated.questions, topic=generated.topic)
            content = normalize_quiz(plain, req.question_count)
            # 出处只能指向资料片段（背景资料不编号），每题必须有
            return attach_sources(content, generated.questions, pieces)

        content = await generate_with_retries(
            attempt,
            attempts=self._settings.quiz_max_attempts,
            default_prompt=DEFAULT_KB_QUIZ_PROMPT,
            conservative_prompt=CONSERVATIVE_KB_QUIZ_PROMPT,
            content_filter=self._filter,
        )
        logger.info(
            "kb quiz for user %s from %d documents, %d pieces (%s), focus=%s, background=%s",
            user_id, len(documents), len(pieces), "agent" if agent_chunks else "fixed", bool(focus), bool(background),
        )
        return Quiz(quiz_id=new_quiz_id(), user_input=focus, source_type="knowledge_base", **content.model_dump())
