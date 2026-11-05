"""出题前联网检索（Tavily Search）。

POST https://api.tavily.com/search，Authorization: Bearer <key>
文档：https://docs.tavily.com/documentation/api-reference/endpoint/search
错误码：401 Key 无效、429 限流、432 / 433 额度用尽、5xx 服务异常。
检索是尽力而为：所有失败都转成 WebSearchError，由调用方降级为不带参考资料出题。
异常信息与日志里只出现状态码，不出现 Key 和请求头。
"""

import logging
from typing import Protocol

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.utils.content_filter import ContentFilter
from app.utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)


class SearchSnippet(BaseModel):
    title: str = ""
    url: str = ""
    content: str = ""


class WebSearchError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class WebSearcher(Protocol):
    async def search(self, query: str) -> list[SearchSnippet]: ...


class TavilySearcher:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http = http_client or httpx.AsyncClient(timeout=settings.tavily_timeout_seconds)

    async def search(self, query: str) -> list[SearchSnippet]:
        s = self._settings
        if not s.tavily_api_key:
            raise WebSearchError("TAVILY_API_KEY 未配置")
        body = {
            "query": query,
            "search_depth": s.tavily_search_depth,
            "max_results": s.tavily_max_results,
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
        }
        try:
            resp = await self._http.post(
                f"{s.tavily_base_url.rstrip('/')}/search",
                json=body,
                headers={"Authorization": f"Bearer {s.tavily_api_key}"},
                timeout=s.tavily_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise WebSearchError(f"Tavily 检索超时（{type(exc).__name__}）") from None
        except httpx.HTTPError as exc:
            # 只保留异常类型：httpx 的异常对象会挂着带 Authorization 头的 request
            raise WebSearchError(f"Tavily 网络错误（{type(exc).__name__}）") from None
        if resp.status_code != 200:
            raise WebSearchError(f"Tavily HTTP {resp.status_code}", status=resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            raise WebSearchError("Tavily 返回非 JSON", status=resp.status_code) from None
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise WebSearchError("Tavily 响应缺少 results", status=resp.status_code)
        snippets: list[SearchSnippet] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            snippets.append(
                SearchSnippet(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    content=str(item.get("content") or ""),
                )
            )
        return snippets

    async def aclose(self) -> None:
        await self._http.aclose()


def _sanitize(text: str) -> str:
    # 去掉尖括号，防止网页内容闭合 / 伪造 <reference>、<material> 分隔标签
    return clean_text(text.replace("<", "").replace(">", ""))


def build_reference(
    snippets: list[SearchSnippet],
    *,
    item_max_chars: int,
    total_max_chars: int,
    content_filter: ContentFilter,
) -> str:
    """把检索结果整理为参考资料文本：`[n] 标题\\n摘要`，条目间空一行；没有可用条目时返回空串。

    单条摘要截断到 item_max_chars；累计长度到 total_max_chars 为止（超出的条目截断或丢弃）。
    命中敏感词的条目整条丢弃。
    """
    parts: list[str] = []
    total = 0
    for snip in snippets:
        title = _sanitize(snip.title).replace("\n", " ")
        content = _sanitize(snip.content)
        if not content:
            continue
        if content_filter.find(title) or content_filter.find(content):
            continue
        content = content[:item_max_chars]
        entry = f"[{len(parts) + 1}] {title}\n{content}" if title else f"[{len(parts) + 1}]\n{content}"
        sep = 2 if parts else 0  # 条目之间的 "\n\n"
        room = total_max_chars - total - sep
        if room <= 0:
            break
        if len(entry) > room:
            entry = entry[:room]
            if "\n" not in entry:  # 连标题都放不下，就不要这一条了
                break
        parts.append(entry)
        total += sep + len(entry)
        if total >= total_max_chars:
            break
    return "\n\n".join(parts)
