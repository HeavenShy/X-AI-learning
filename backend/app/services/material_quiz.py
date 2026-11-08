"""网页 / 视频出题共用的后半段：块 → AI 判断主题与范围 → 编号材料 → 出题 → 校验 + 出处 → 重试。

    范围判断（WebScopeJudge，按 kind 换措辞）：learnable=false → 4032；给出知识点和块（按重要性）
         模型报错 / 超时 / 块编号全部无效 → 按原文顺序取块，不带知识点（降级，照常出题）
    → AI 选的块合计不到材料上限的 1/3 时按原文顺序补上其余块
    → 按优先级截到 material_max_chars，按原文顺序编号成材料（视频的片段带时间段标签）
    → 共享重试循环出题（kind 对应的 v1 常规 / v2 保守），每题必须有出处（attach_sources required=True）
    → 出处补上 url（网页地址 / B 站链接）和 start_seconds（视频）

调用方负责取来源（抓网页 / 转写视频）、切块和敏感词过滤，以及组装最终的 Quiz。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import Settings
from app.core.exceptions import BizError, ErrorCode
from app.llm.output_schemas import WebPageScope
from app.llm.web_quiz_chain import WebQuizGenerator
from app.llm.web_scope_chain import WebScopeJudge
from app.models.quiz import QuizContent
from app.prompts.kb_quiz_prompt import MaterialPiece, format_materials
from app.prompts.web_quiz_prompt import QUIZ_PROMPTS_BY_KIND
from app.services.kb_materials import attach_sources, fit_materials, strip_sources
from app.services.quiz_retry import generate_with_retries
from app.services.quiz_validator import DEFAULT_TOPIC, normalize_quiz, normalize_topic
from app.utils.content_filter import ContentFilter
from app.utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)

SourceKind = Literal["web", "video"]

MSG_NOT_LEARNABLE = {
    "web": "AI 读完觉得这个网页没有可以出题的知识内容{reason}。换一篇文章链接试试。",
    "video": "AI 听完觉得这段视频没有可以出题的知识讲解{reason}。换一段讲知识的视频试试。",
}

MAX_POINTS = 8
# 知识点只进出题 Prompt，截断只为防止异常长的输出
POINT_MAX_CHARS = 40
REASON_MAX_CHARS = 40
# AI 选的块合计不到材料上限的这个比例时，按原文顺序补上其余块，避免材料太少出不够题
MIN_SELECTED_RATIO = 1 / 3


def format_clock(seconds: float) -> str:
    """秒 → mm:ss（满 1 小时为 h:mm:ss）。"""
    total = max(0, int(seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# 用摘录开头多少个字（去空白后）去文字稿里定位
QUOTE_PROBE_CHARS = 12


def _squash(text: str) -> str:
    return "".join(clean_text(text).split())


@dataclass(frozen=True)
class Block:
    """一段正文 / 文字稿。视频的块有起止秒数，parts 是拼成这块的各段（起始秒数, 文字）。"""

    text: str
    start: float | None = None
    end: float | None = None
    parts: tuple[tuple[float, str], ...] = ()

    def time_of(self, quote: str) -> float | None:
        """摘录在块里哪一段：返回那一段的起始秒数；找不到返回块的起始秒数；网页的块返回 None。"""
        if self.start is None:
            return None
        probe = _squash(quote)[:QUOTE_PROBE_CHARS]
        if not probe or not self.parts:
            return self.start
        squashed = [_squash(t) for _, t in self.parts]
        pos = "".join(squashed).find(probe)
        if pos < 0:
            return self.start
        offset = 0
        for (start, _), s in zip(self.parts, squashed):
            offset += len(s)
            if pos < offset:
                return start
        return self.start

    @property
    def label(self) -> str | None:
        if self.start is None:
            return None
        end = self.end if self.end is not None else self.start
        return f"{format_clock(self.start)}–{format_clock(end)}"


@dataclass(frozen=True)
class SourceDoc:
    kind: SourceKind
    # 出处的 document_id（web_xxx / video_xxx）
    doc_id: str
    # 网页标题 / 视频名（出处的 document_name）
    title: str
    # 站点 host / 视频来源（“B 站”“上传的视频”）
    site: str
    blocks: list[Block]
    # 出处带的链接：网页地址 / B 站链接；上传的视频为 None
    url: str | None = None


@dataclass
class Scope:
    """范围判断的结果：块下标（从 0 起）按优先级排列；mode 用于日志。"""

    order: list[int]
    knowledge_points: list[str]
    mode: str
    topic: str = ""


@dataclass
class MaterialQuizResult:
    content: QuizContent
    scope: Scope
    pieces: list[MaterialPiece] = field(default_factory=list)
    scope_seconds: float = 0.0


class MaterialQuizEngine:
    def __init__(
        self,
        judge: WebScopeJudge,
        generator: WebQuizGenerator,
        *,
        settings: Settings,
        content_filter: ContentFilter,
        material_max_chars: int,
    ):
        self._judge = judge
        self._generator = generator
        self._settings = settings
        self._filter = content_filter
        self._max_chars = material_max_chars

    # ---------- 范围 ----------

    def _clean_points(self, raw: list[str]) -> list[str]:
        points: list[str] = []
        for p in raw:
            p = " ".join(clean_text(p).split())[:POINT_MAX_CHARS]
            if p and p not in points and not self._filter.find(p):
                points.append(p)
        return points[:MAX_POINTS]

    def _top_up(self, picked: list[int], blocks: list[Block]) -> list[int]:
        budget = min(self._max_chars, sum(len(b.text) for b in blocks))
        if sum(len(blocks[i].text) for i in picked) >= budget * MIN_SELECTED_RATIO:
            return picked
        chosen = set(picked)
        return picked + [i for i in range(len(blocks)) if i not in chosen]

    @staticmethod
    def _judge_text(block: Block) -> str:
        # 视频的块带上时间段，范围判断能看出前后顺序
        return f"{block.label} {block.text}" if block.label else block.text

    async def scope(self, doc: SourceDoc, focus: str) -> Scope:
        blocks = doc.blocks
        sequential = list(range(len(blocks)))
        full = sum(len(b.text) for b in blocks) <= self._max_chars
        try:
            result: WebPageScope = await asyncio.wait_for(
                self._judge.judge(
                    title=doc.title,
                    site=doc.site,
                    blocks=[self._judge_text(b) for b in blocks],
                    focus=focus,
                    full=full,
                    kind=doc.kind,
                ),
                timeout=self._settings.web_scope_timeout_seconds,
            )
        except TimeoutError:
            return Scope(sequential, [], "fallback(timeout)")
        except Exception as exc:  # noqa: BLE001 —— 范围判断是锦上添花，任何异常都降级为按原文顺序取材
            return Scope(sequential, [], f"fallback({type(exc).__name__})")
        if not result.learnable:
            reason = " ".join(clean_text(result.reason).split()).rstrip("。.！!")[:REASON_MAX_CHARS]
            if reason and self._filter.find(reason):
                reason = ""
            logger.info("%s scope %s: not learnable", doc.kind, doc.site)
            raise BizError(
                ErrorCode.PAGE_NO_CONTENT, MSG_NOT_LEARNABLE[doc.kind].format(reason=f"：{reason}" if reason else "")
            )
        points = self._clean_points(result.knowledge_points)
        picked = list(dict.fromkeys(n - 1 for n in result.block_ids if 1 <= n <= len(blocks)))
        if not picked:
            return Scope(sequential, points, "fallback(no_blocks)", topic=result.topic)
        return Scope(self._top_up(picked, blocks), points, "ai", topic=result.topic)

    # ---------- 材料与出处 ----------

    def pieces(self, doc: SourceDoc, order: list[int]) -> list[MaterialPiece]:
        rows = [
            {
                "id": i + 1,
                "document_id": doc.doc_id,
                "seq": i,
                "page": None,
                "text": doc.blocks[i].text,
                "label": doc.blocks[i].label,
            }
            for i in order
        ]
        return fit_materials(rows, names={doc.doc_id: doc.title}, doc_order=[doc.doc_id], max_chars=self._max_chars)

    @staticmethod
    def _source_extra(doc: SourceDoc):
        def extra(piece: MaterialPiece, quote: str) -> dict:
            block = doc.blocks[piece.chunk_id - 1]
            data: dict = {"url": doc.url}
            at = block.time_of(quote)
            if at is not None:
                data["start_seconds"] = int(at)
            return data

        return extra

    # ---------- 出题 ----------

    async def generate(
        self, doc: SourceDoc, *, focus: str, question_count: int, difficulty: str
    ) -> MaterialQuizResult:
        start = time.perf_counter()
        scope = await self.scope(doc, focus)
        scope_seconds = time.perf_counter() - start
        pieces = self.pieces(doc, scope.order)
        materials = format_materials(pieces)
        default_prompt, conservative_prompt = QUIZ_PROMPTS_BY_KIND[doc.kind]
        extra = self._source_extra(doc)

        async def attempt(version: str) -> QuizContent:
            generated = await self._generator.generate(
                materials=materials,
                knowledge_points=scope.knowledge_points,
                focus=focus,
                question_count=question_count,
                difficulty=difficulty,
                prompt_version=version,
            )
            plain = strip_sources(generated.title, generated.summary, generated.questions, topic=generated.topic)
            content = normalize_quiz(plain, question_count)
            return attach_sources(content, generated.questions, pieces, source_extra=extra)

        content = await generate_with_retries(
            attempt,
            attempts=self._settings.quiz_max_attempts,
            default_prompt=default_prompt,
            conservative_prompt=conservative_prompt,
            content_filter=self._filter,
        )
        # 出题模型没给大类时，用范围判断给的大类
        if content.topic == DEFAULT_TOPIC:
            content = content.model_copy(update={"topic": normalize_topic(scope.topic)})
        return MaterialQuizResult(content=content, scope=scope, pieces=pieces, scope_seconds=scope_seconds)
