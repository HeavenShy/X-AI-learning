"""出题前的检索规划 Agent：模型决定查知识库、联网、都查还是都不查，以及查询词。

两段式的第一段：这里只收集资料，出题、校验、重试沿用原链路。手写循环，不依赖 Agent 框架：

    for 第 1..agent_max_rounds 轮:
        模型（只绑定本次可用的工具，tool_choice=auto）→ 没有工具调用就结束
        最后一轮的工具调用不执行
        逐个执行工具调用（同一条消息里的并行调用也逐个计数），结果作为 ToolMessage 追加
        达到工具总数或联网次数上限就结束

- 不合法的调用（未知工具、参数不是合法 JSON、缺 query）：回一条错误 ToolMessage，不计次数、不算失败；
- 超出上限的调用：回“已达上限”，不执行；
- 联网查询词清洗并截到 agent_web_query_max_chars，命中敏感词不执行但计入次数；
- 工具执行失败（Embedding / Tavily 报错）：回“检索失败”，计入次数，不算规划失败；
- 模型调用报错、整体超过 agent_timeout_seconds：抛 PlanningError，调用方退回固定规则。

Agent 只看到结果预览（片段前 200 字、摘要前 150 字），完整内容留在 RetrievalResult 里交给出题。
日志只记入口、工具、次数、条数、耗时与降级原因，不记学习内容、查询词、正文和 Key。
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from pydantic import ValidationError

from app.agent.tools import KB_TOOL, TOOL_MODELS, WEB_TOOL
from app.core.config import Settings
from app.prompts.retrieval_agent_prompt import CatalogItem, PlanEntry, build_retrieval_agent_messages, strip_tags
from app.services.web_search import SearchSnippet
from app.utils.content_filter import ContentFilter
from app.utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)

KB_PREVIEW_CHARS = 200
WEB_PREVIEW_CHARS = 150

MSG_LIMIT = "已达到本次检索次数上限，这次调用没有执行。"
MSG_BAD_CALL = "工具调用不合法（工具名或参数不对），没有执行。可用工具：{tools}，参数只有 query。"
MSG_QUERY_NOT_ALLOWED = "查询词不合规，这次检索没有执行。"
MSG_TOOL_FAILED = "检索失败，暂时没有结果。"
MSG_NO_RESULTS = "没有检索到相关内容。"

_SHORT = {KB_TOOL: "kb", WEB_TOOL: "web"}


@dataclass(frozen=True)
class KbChunk:
    """知识库检索命中的片段（正文以 MySQL 为准，已排除 flagged）。"""

    id: int
    document_id: str
    document_name: str
    seq: int
    page: int | None
    text: str


KbSearch = Callable[[str], Awaitable[list[KbChunk]]]
WebSearchFn = Callable[[str], Awaitable[list[SearchSnippet]]]


@dataclass
class PlanContext:
    """entry=home：text 是学习内容；entry=kb：text 是重点（可为空）。工具为 None 表示本次不可用。"""

    entry: Literal["home", "kb"]
    text: str
    kb_search: KbSearch | None = None
    web_search: WebSearchFn | None = None
    catalog: list[CatalogItem] = field(default_factory=list)

    @property
    def prompt_entry(self) -> PlanEntry:
        if self.entry == "home":
            return "home"
        return "kb_focus" if self.text else "kb_spread"

    @property
    def tool_names(self) -> list[str]:
        return [n for n, fn in ((KB_TOOL, self.kb_search), (WEB_TOOL, self.web_search)) if fn is not None]


@dataclass
class RetrievalResult:
    # 按首次命中顺序去重（片段按 id，网页按 url，无 url 按标题）
    kb_chunks: list[KbChunk] = field(default_factory=list)
    web_snippets: list[SearchSnippet] = field(default_factory=list)
    kb_calls: int = 0
    web_calls: int = 0
    rounds: int = 0


class PlanningError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def log_plan_skipped(entry: str, reason: str) -> None:
    """没有运行检索规划（开关关闭 / 没有可用数据源）时也记一条，便于对照。"""
    logger.info("retrieval plan entry=%s skipped fallback=%s", entry, reason)


class _Run:
    """一次规划的可变状态。"""

    def __init__(self, ctx: PlanContext):
        self.ctx = ctx
        self.result = RetrievalResult()
        self._kb_seen: dict[int, int] = {}  # chunk id → 预览编号
        self._web_seen: dict[str, int] = {}

    @property
    def total_calls(self) -> int:
        return self.result.kb_calls + self.result.web_calls

    def add_kb(self, chunks: list[KbChunk]) -> list[tuple[int, KbChunk]]:
        numbered = []
        for c in chunks:
            if c.id not in self._kb_seen:
                self.result.kb_chunks.append(c)
                self._kb_seen[c.id] = len(self.result.kb_chunks)
            numbered.append((self._kb_seen[c.id], c))
        return numbered

    def add_web(self, snippets: list[SearchSnippet]) -> list[tuple[int, SearchSnippet]]:
        numbered = []
        for s in snippets:
            key = s.url or f"title:{s.title}"
            if key not in self._web_seen:
                self.result.web_snippets.append(s)
                self._web_seen[key] = len(self.result.web_snippets)
            numbered.append((self._web_seen[key], s))
        return numbered


def _one_line(text: str) -> str:
    return " ".join(strip_tags(text).split())


class RetrievalPlanner:
    def __init__(self, llm: BaseChatModel, *, settings: Settings, content_filter: ContentFilter):
        self._llm = llm
        self._settings = settings
        self._filter = content_filter

    async def plan(self, ctx: PlanContext) -> RetrievalResult:
        if not ctx.tool_names:
            raise ValueError("plan() needs at least one available tool")
        run = _Run(ctx)
        start = time.perf_counter()
        try:
            await asyncio.wait_for(self._loop(run), timeout=self._settings.agent_timeout_seconds)
        except TimeoutError:
            self._log(run, start, fallback="timeout")
            raise PlanningError("timeout") from None
        except Exception as exc:  # noqa: BLE001 —— 模型报错等任何异常都退回固定规则
            self._log(run, start, fallback="model_error", detail=type(exc).__name__)
            raise PlanningError("model_error") from exc
        self._log(run, start, fallback="-")
        return run.result

    async def _loop(self, run: _Run) -> None:
        s = self._settings
        ctx = run.ctx
        tools = [TOOL_MODELS[n] for n in ctx.tool_names]
        model = self._llm.bind_tools(tools, tool_choice="auto")
        messages: list[BaseMessage] = build_retrieval_agent_messages(
            ctx.prompt_entry,
            text=ctx.text,
            catalog=ctx.catalog,
            kb_available=ctx.kb_search is not None,
            web_available=ctx.web_search is not None,
            max_tool_calls=s.agent_max_tool_calls,
            max_web_searches=s.agent_max_web_searches,
        )
        for round_no in range(1, s.agent_max_rounds + 1):
            ai = await model.ainvoke(messages)
            run.result.rounds = round_no
            if not isinstance(ai, AIMessage):
                raise TypeError(f"unexpected model output {type(ai).__name__}")
            calls = [(c["id"], c["name"], c["args"]) for c in ai.tool_calls]
            calls += [(c.get("id"), c.get("name"), None) for c in ai.invalid_tool_calls]
            if not calls or round_no == s.agent_max_rounds:
                # 不再调用工具，或已是最后一轮（这一轮的工具调用不执行）
                return
            messages.append(ai)
            for call_id, name, args in calls:
                content = await self._execute(run, name, args)
                messages.append(ToolMessage(content=content, tool_call_id=call_id or ""))
            if run.total_calls >= s.agent_max_tool_calls or run.result.web_calls >= s.agent_max_web_searches:
                return

    async def _execute(self, run: _Run, name: str | None, args: dict | None) -> str:
        s = self._settings
        ctx = run.ctx
        if name not in ctx.tool_names or not isinstance(args, dict):
            return MSG_BAD_CALL.format(tools="、".join(ctx.tool_names))
        try:
            query = clean_text(TOOL_MODELS[name].model_validate(args).query)
        except ValidationError:
            return MSG_BAD_CALL.format(tools="、".join(ctx.tool_names))
        if not query:
            return MSG_BAD_CALL.format(tools="、".join(ctx.tool_names))
        if run.total_calls >= s.agent_max_tool_calls:
            return MSG_LIMIT
        if name == WEB_TOOL:
            if run.result.web_calls >= s.agent_max_web_searches:
                return MSG_LIMIT
            run.result.web_calls += 1
            query = query[: s.agent_web_query_max_chars]
            if self._filter.find(query):
                return MSG_QUERY_NOT_ALLOWED
            try:
                snippets = await ctx.web_search(query)
            except Exception as exc:  # noqa: BLE001 —— 检索失败不算规划失败
                self._log_tool_failure(name, exc)
                return MSG_TOOL_FAILED
            return self._web_preview(run.add_web(snippets))
        run.result.kb_calls += 1
        query = query[: s.agent_kb_query_max_chars]
        try:
            chunks = await ctx.kb_search(query)
        except Exception as exc:  # noqa: BLE001
            self._log_tool_failure(name, exc)
            return MSG_TOOL_FAILED
        return self._kb_preview(run.add_kb(chunks))

    @staticmethod
    def _kb_preview(numbered: list[tuple[int, KbChunk]]) -> str:
        if not numbered:
            return MSG_NO_RESULTS
        lines = []
        for n, c in numbered:
            where = f"《{_one_line(c.document_name)}》" + (f"第 {c.page} 页" if c.page is not None else "")
            lines.append(f"[K{n}] {where}：{_one_line(c.text)[:KB_PREVIEW_CHARS]}")
        return "\n".join(lines)

    def _web_preview(self, numbered: list[tuple[int, SearchSnippet]]) -> str:
        lines = []
        for n, snip in numbered:
            title, content = _one_line(snip.title), _one_line(snip.content)
            if not content or self._filter.find(title) or self._filter.find(content):
                continue
            lines.append(f"[W{n}] {title}：{content[:WEB_PREVIEW_CHARS]}")
        return "\n".join(lines) or MSG_NO_RESULTS

    @staticmethod
    def _log_tool_failure(name: str, exc: Exception) -> None:
        logger.warning(
            "retrieval tool %s failed: %s status=%s", _SHORT[name], type(exc).__name__, getattr(exc, "status", None)
        )

    @staticmethod
    def _log(run: _Run, start: float, *, fallback: str, detail: str = "") -> None:
        r = run.result
        line = (
            "retrieval plan entry=%s tools=[%s] calls=kb:%d,web:%d results=kb:%d,web:%d rounds=%d %.1fs fallback=%s%s"
        )
        args = (
            run.ctx.entry,
            ",".join(_SHORT[n] for n in run.ctx.tool_names),
            r.kb_calls,
            r.web_calls,
            len(r.kb_chunks),
            len(r.web_snippets),
            r.rounds,
            time.perf_counter() - start,
            fallback,
            f" ({detail})" if detail else "",
        )
        if fallback == "-":
            logger.info(line, *args)
        else:
            logger.warning(line, *args)
