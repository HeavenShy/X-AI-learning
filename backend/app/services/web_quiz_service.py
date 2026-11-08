"""网页出题：读网页 → 切块 → AI 判断主题与范围 → 只依据网页出题 → 校验 + 出处 → 重试。

    校验重点（4003）→ PageReader.read（本地优先、Tavily 兜底、缓存；失败 4030–4033）→ 标题过敏感词（4003）
    → 正文按段落切块（不重叠），命中敏感词的块丢弃
    → MaterialQuizEngine（material_quiz.py）：范围判断、取材料、出题、出处（带网址）

结果 source_type=web；日志只记 host、抓取方式、字数、块数、范围判断结果，不记网址路径和正文。
"""

import hashlib
import logging
import time

import httpx

from app.core.config import Settings
from app.core.exceptions import BizError, ErrorCode
from app.llm.web_quiz_chain import WebQuizGenerator
from app.llm.web_scope_chain import WebScopeJudge
from app.models.quiz import Quiz
from app.models.web import WebPreview, WebQuizRequest
from app.rag.parsing import Segment, chunk_segments
from app.services.material_quiz import Block, MaterialQuizEngine, SourceDoc
from app.services.web_page import PageReader, WebFetchError, WebPage, to_biz_error
from app.utils.content_filter import ContentFilter
from app.utils.id_generator import new_quiz_id
from app.utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)

MSG_FOCUS_NOT_ALLOWED = "重点内容涉及不适合出题的话题，换个说法试试。"
MSG_PAGE_NOT_ALLOWED = "这个网页涉及不适合出题的话题，换一篇试试。"

# 预览的阅读时长：按每分钟约 450 字估算
READ_CHARS_PER_MINUTE = 450


def read_minutes(char_count: int) -> int:
    return max(1, round(char_count / READ_CHARS_PER_MINUTE))


def web_document_id(url: str) -> str:
    return "web_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def check_focus(raw: str, content_filter: ContentFilter) -> str:
    """清洗重点；命中敏感词 4003。网页、视频出题共用。"""
    focus = clean_text(raw)
    if focus and content_filter.find(focus):
        raise BizError(ErrorCode.CONTENT_NOT_ALLOWED, MSG_FOCUS_NOT_ALLOWED)
    return focus


class WebQuizService:
    def __init__(
        self,
        reader: PageReader,
        judge: WebScopeJudge,
        generator: WebQuizGenerator,
        *,
        settings: Settings,
        content_filter: ContentFilter,
    ):
        self._reader = reader
        self._settings = settings
        self._filter = content_filter
        self._engine = MaterialQuizEngine(
            judge,
            generator,
            settings=settings,
            content_filter=content_filter,
            material_max_chars=settings.web_material_max_chars,
        )

    async def _read(self, url: str) -> WebPage:
        try:
            page = await self._reader.read(url)
        except WebFetchError as exc:
            raise to_biz_error(exc) from None
        if self._filter.find(page.title):
            raise BizError(ErrorCode.CONTENT_NOT_ALLOWED, MSG_PAGE_NOT_ALLOWED)
        return page

    async def preview(self, url: str) -> WebPreview:
        page = await self._read(url)
        return WebPreview(
            url=page.url,
            site=page.site,
            title=page.title,
            char_count=page.char_count,
            read_minutes=read_minutes(page.char_count),
            via=page.via,
        )

    def _blocks(self, text: str) -> tuple[list[str], int]:
        """按段落切块（单个换行也算分段），不重叠；返回 (可用块, 丢弃的敏感块数)。"""
        paragraphs = text.replace("\n", "\n\n")
        chunks = chunk_segments(
            [Segment(page=None, text=paragraphs)], chunk_chars=self._settings.kb_chunk_chars, overlap=0
        )
        blocks, flagged = [], 0
        for c in chunks:
            if self._filter.find(c.text):
                flagged += 1
            else:
                blocks.append(c.text)
        return blocks, flagged

    async def generate(self, req: WebQuizRequest) -> Quiz:
        start = time.perf_counter()
        focus = check_focus(req.focus, self._filter)
        page = await self._read(req.url)
        blocks, flagged = self._blocks(page.text)
        if not blocks:
            raise BizError(ErrorCode.CONTENT_NOT_ALLOWED, MSG_PAGE_NOT_ALLOWED)
        doc = SourceDoc(
            kind="web",
            doc_id=web_document_id(page.url),
            title=page.title,
            site=page.site,
            blocks=[Block(text=b) for b in blocks],
            url=page.url,
        )
        result = await self._engine.generate(
            doc, focus=focus, question_count=req.question_count, difficulty=req.difficulty
        )
        logger.info(
            "web quiz %s via=%s chars=%d blocks=%d flagged=%d pieces=%d scope=%s points=%d scope_s=%.1f total_s=%.1f",
            httpx.URL(page.url).host, page.via, page.char_count, len(blocks), flagged, len(result.pieces),
            result.scope.mode, len(result.scope.knowledge_points), result.scope_seconds, time.perf_counter() - start,
        )
        return Quiz(
            quiz_id=new_quiz_id(),
            user_input=focus or page.title,
            source_type="web",
            **result.content.model_dump(),
        )
