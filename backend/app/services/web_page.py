"""网页出题的抓取与正文提取。

本地优先，Tavily Extract 兜底：

    PageReader.read(url)
        规范化 URL（invalid_url）→ 查缓存
        LocalPageFetcher.fetch：SSRF 校验 → GET（手动跟重定向，每一跳重新校验）→ 限大小 / 类型 → trafilatura 提正文
        本地失败且原因是 no_text / http_blocked / unreachable，并且配了 Tavily → TavilyExtractor.extract
        成功结果按请求地址和最终地址缓存 web_page_cache_seconds，预览和出题只抓一次

SSRF 防护：只允许 http / https、端口 80 / 443、URL 里不能带用户名密码；域名解析出的每个 IP 都必须是公网地址
（ipaddress.is_global，IPv4 映射的 IPv6 先还原）。残留风险是 DNS rebinding（校验与连接之间解析结果变化），
见设计文档 7.9。

错误都转成 WebFetchError(kind)，message 是给用户看的话；日志只记 host、状态码、异常类型，不记路径和正文。
"""

import asyncio
import ipaddress
import logging
import socket
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from app.core.config import Settings
from app.core.exceptions import BizError, ErrorCode
from app.rag.parsing import decode_text
from app.utils.text_cleaner import clean_text, visible_length

logger = logging.getLogger(__name__)

FetchErrorKind = Literal[
    "invalid_url", "blocked_address", "unreachable", "not_found", "http_blocked", "not_html", "too_large", "no_text"
]

MESSAGES: dict[str, str] = {
    "invalid_url": "链接格式不对：请粘贴完整的网页地址，以 http:// 或 https:// 开头。",
    "blocked_address": "这个地址不能访问：只支持公开的网页链接。",
    "unreachable": "网页打不开：可能是网址有误、网站暂时无法访问或网络超时。稍后再试，或换一个链接。",
    "not_found": "网页不存在，可能已经被删除了，检查一下链接。",
    "http_blocked": "这个网站拒绝了访问，可能要登录才能看。换一个公开的链接，或把要学的段落粘贴到首页出题。",
    "not_html": "这个链接不是网页（可能是图片、视频或下载文件），换一个文章链接试试。",
    "not_html_pdf": "这是一个 PDF 文件，不是网页：可以下载后到“我的知识库”上传，再用资料出题。",
    "too_large": "网页太大了，读不下来，换一个链接试试。",
    "no_text": "这个网页读不出正文：可能要登录、内容是动态加载的，或页面上没有文章。可以把要学的段落粘贴到首页出题。",
}

ERROR_CODES: dict[str, ErrorCode] = {
    "invalid_url": ErrorCode.URL_INVALID,
    "blocked_address": ErrorCode.URL_INVALID,
    "unreachable": ErrorCode.PAGE_UNREACHABLE,
    "not_found": ErrorCode.PAGE_UNREACHABLE,
    "http_blocked": ErrorCode.PAGE_UNREACHABLE,
    "no_text": ErrorCode.PAGE_NO_CONTENT,
    "not_html": ErrorCode.PAGE_NOT_SUPPORTED,
    "too_large": ErrorCode.PAGE_NOT_SUPPORTED,
}

# 本地读不出来时值得换 Tavily 试一次的原因（地址不合法 / 不是网页 / 太大换了也没用）
FALLBACK_KINDS = {"no_text", "http_blocked", "unreachable"}

ALLOWED_PORTS = {None, 80, 443}
HTML_TYPES = {"text/html", "application/xhtml+xml"}
TEXT_TYPES = {"text/plain"}
TITLE_MAX_CHARS = 80
# 常见的手机浏览器 UA：部分站点（含公众号文章）对非浏览器 UA 返回空页面；不带任何用户信息
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class WebFetchError(Exception):
    def __init__(self, kind: str, message: str | None = None, *, status: int | None = None):
        super().__init__(message or MESSAGES.get(kind, MESSAGES["unreachable"]))
        self.kind = kind
        self.message = str(self)
        self.status = status


def to_biz_error(exc: WebFetchError) -> BizError:
    return BizError(ERROR_CODES.get(exc.kind, ErrorCode.PAGE_UNREACHABLE), exc.message)


@dataclass(frozen=True)
class WebPage:
    url: str
    site: str
    title: str
    text: str
    char_count: int
    via: Literal["local", "tavily"]


# ---------- URL 与地址校验 ----------


def normalize_url(raw: str) -> str:
    """去空白；没写协议时补 https://。格式不对、协议 / 端口不允许、带用户名密码时抛 invalid_url。"""
    text = (raw or "").strip()
    if not text or any(ch.isspace() for ch in text):
        raise WebFetchError("invalid_url")
    if "://" not in text:
        text = f"https://{text}"
    try:
        url = httpx.URL(text)
    except Exception:  # noqa: BLE001 —— httpx.InvalidURL 等
        raise WebFetchError("invalid_url") from None
    host = url.host
    # 需要像个域名或 IP：localhost 这类单段主机名不接受
    if url.scheme not in ("http", "https") or not host or ("." not in host and ":" not in host):
        raise WebFetchError("invalid_url")
    if url.userinfo:
        raise WebFetchError("invalid_url")
    if url.port not in ALLOWED_PORTS:
        raise WebFetchError("blocked_address")
    return str(url.copy_with(fragment=None))


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def system_resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def check_public(url: httpx.URL, resolve: Resolver) -> None:
    """URL 的主机必须只解析到公网地址；解析失败判为打不开。"""
    if url.scheme not in ("http", "https") or url.port not in ALLOWED_PORTS or url.userinfo:
        raise WebFetchError("blocked_address")
    host = url.host
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = await resolve(host, url.port or (443 if url.scheme == "https" else 80))
        except (OSError, UnicodeError):
            raise WebFetchError("unreachable") from None
    if not addresses or not all(is_public_ip(a) for a in addresses):
        raise WebFetchError("blocked_address")


# ---------- 正文提取 ----------


def _one_line(text: str) -> str:
    return " ".join(clean_text(text).split())


def _title_from_text(text: str) -> str:
    for line in text.split("\n"):
        line = _one_line(line.lstrip("#").strip())
        if line:
            # 第一行太长多半是正文段落，不当标题
            return line if len(line) <= 60 else ""
    return ""


def extract_html(body: bytes, url: str) -> tuple[str, str, str]:
    """trafilatura 提取 (标题, 站点名, 正文)；提不出来时都为空串。CPU 密集，调用方放线程池。"""
    import trafilatura  # 延迟导入：启动更快，测试不用它的用例也不加载 lxml

    doc = trafilatura.bare_extraction(
        body, url=url, with_metadata=True, include_comments=False, include_tables=True, include_images=False
    )
    if doc is None:
        return "", "", ""
    return str(doc.title or ""), str(doc.sitename or ""), str(doc.text or "")


def finish_page(*, url: str, title: str, text: str, via: str, settings: Settings) -> WebPage:
    """清洗正文、截到上限、判断字数，整理标题。正文太短抛 no_text。"""
    text = clean_text(text)[: settings.web_page_max_chars]
    if visible_length(text) < settings.web_page_min_chars:
        raise WebFetchError("no_text")
    host = httpx.URL(url).host
    title = _one_line(title).replace("<", "").replace(">", "")[:TITLE_MAX_CHARS] or _title_from_text(text) or host
    return WebPage(url=url, site=host, title=title, text=text, char_count=visible_length(text), via=via)


# ---------- 本地抓取 ----------


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> WebPage: ...


class LocalPageFetcher:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        resolve: Resolver = system_resolve,
    ):
        self._settings = settings
        # 不自动跟重定向：每一跳都要重新做地址校验
        self._http = http_client or httpx.AsyncClient(follow_redirects=False, timeout=settings.web_fetch_timeout_seconds)
        self._resolve = resolve

    async def fetch(self, url: str) -> WebPage:
        try:
            final_url, body, media_type = await asyncio.wait_for(
                self._download(url), timeout=self._settings.web_fetch_timeout_seconds
            )
        except TimeoutError:
            raise WebFetchError("unreachable") from None
        if media_type in TEXT_TYPES:
            text = decode_text(body) or ""
            title = _title_from_text(text)
        else:
            title, _site, text = await asyncio.to_thread(extract_html, body, final_url)
        return finish_page(url=final_url, title=title, text=text, via="local", settings=self._settings)

    async def _download(self, url: str) -> tuple[str, bytes, str]:
        s = self._settings
        current = httpx.URL(url)
        for _ in range(s.web_fetch_max_redirects + 1):
            await check_public(current, self._resolve)
            try:
                async with self._http.stream(
                    "GET",
                    current,
                    headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"},
                    timeout=s.web_fetch_timeout_seconds,
                ) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise WebFetchError("unreachable", status=resp.status_code)
                        current = current.join(location)
                        continue
                    self._check_status(resp.status_code)
                    media_type = self._media_type(resp)
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > s.web_fetch_max_bytes:
                        raise WebFetchError("too_large")
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body += chunk
                        if len(body) > s.web_fetch_max_bytes:
                            raise WebFetchError("too_large")
                    if not media_type:
                        media_type = "text/html" if bytes(body[:512]).lstrip().startswith(b"<") else ""
                        if not media_type:
                            raise WebFetchError("not_html")
                    return str(resp.url), bytes(body), media_type
            except httpx.TimeoutException:
                raise WebFetchError("unreachable") from None
            except httpx.HTTPError as exc:
                logger.info("web fetch %s network error: %s", current.host, type(exc).__name__)
                raise WebFetchError("unreachable") from None
        raise WebFetchError("unreachable", "网页跳转次数太多，打不开。换一个链接试试。")

    @staticmethod
    def _check_status(status: int) -> None:
        if status == 200:
            return
        if status in (404, 410):
            raise WebFetchError("not_found", status=status)
        if status in (401, 403, 429) or status >= 500:
            raise WebFetchError("http_blocked", status=status)
        raise WebFetchError("unreachable", status=status)

    @staticmethod
    def _media_type(resp: httpx.Response) -> str:
        """返回 text/html 等；没有 Content-Type 时返回空串（由正文开头判断）。类型不支持时抛 not_html。"""
        raw = resp.headers.get("content-type", "")
        media_type = raw.split(";", 1)[0].strip().lower()
        if not media_type:
            return ""
        if media_type in HTML_TYPES or media_type in TEXT_TYPES:
            return media_type
        if media_type == "application/pdf":
            raise WebFetchError("not_html", MESSAGES["not_html_pdf"])
        raise WebFetchError("not_html")

    async def aclose(self) -> None:
        await self._http.aclose()


# ---------- Tavily Extract 兜底 ----------


class TavilyExtractor:
    """POST {tavily_base_url}/extract：由 Tavily 抓取页面（能处理部分动态页面），basic 每 5 个成功 URL 1 credit。"""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http = http_client or httpx.AsyncClient(timeout=settings.web_fetch_timeout_seconds + 10)

    async def extract(self, url: str) -> WebPage:
        s = self._settings
        if not s.tavily_api_key:
            raise WebFetchError("unreachable")
        try:
            resp = await self._http.post(
                f"{s.tavily_base_url.rstrip('/')}/extract",
                json={"urls": [url], "extract_depth": "basic", "format": "text"},
                headers={"Authorization": f"Bearer {s.tavily_api_key}"},
                timeout=s.web_fetch_timeout_seconds + 10,
            )
        except httpx.HTTPError as exc:
            # 只保留异常类型：httpx 的异常对象会挂着带 Authorization 头的 request
            raise WebFetchError("unreachable", f"Tavily Extract 网络错误（{type(exc).__name__}）") from None
        if resp.status_code != 200:
            raise WebFetchError("unreachable", f"Tavily Extract HTTP {resp.status_code}", status=resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            raise WebFetchError("unreachable", "Tavily Extract 返回非 JSON") from None
        results = data.get("results") if isinstance(data, dict) else None
        item = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else None
        if item is None:
            raise WebFetchError("no_text")
        text = str(item.get("raw_content") or "")
        final_url = str(item.get("url") or url)
        try:
            httpx.URL(final_url)
        except Exception:  # noqa: BLE001
            final_url = url
        return finish_page(url=final_url, title=str(item.get("title") or ""), text=text, via="tavily", settings=s)

    async def aclose(self) -> None:
        await self._http.aclose()


# ---------- 组合：缓存 + 本地优先 + 兜底 ----------


class PageReader:
    def __init__(
        self,
        settings: Settings,
        *,
        fetcher: PageFetcher,
        extractor: TavilyExtractor | None = None,
        clock: Callable[[], float] = time.monotonic,
        cache_size: int = 64,
    ):
        self._settings = settings
        self._fetcher = fetcher
        self._extractor = extractor
        self._clock = clock
        self._cache: OrderedDict[str, tuple[float, WebPage]] = OrderedDict()
        self._cache_size = cache_size
        self._sem = asyncio.Semaphore(max(1, settings.web_fetch_concurrency))

    def _cached(self, url: str) -> WebPage | None:
        hit = self._cache.get(url)
        if hit is None:
            return None
        expires, page = hit
        if expires < self._clock():
            self._cache.pop(url, None)
            return None
        self._cache.move_to_end(url)
        return page

    def _remember(self, keys: list[str], page: WebPage) -> None:
        expires = self._clock() + self._settings.web_page_cache_seconds
        for key in dict.fromkeys(keys):
            self._cache[key] = (expires, page)
            self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    async def read(self, raw_url: str) -> WebPage:
        url = normalize_url(raw_url)
        page = self._cached(url)
        if page is not None:
            return page
        host = httpx.URL(url).host
        start = time.perf_counter()
        async with self._sem:
            try:
                page = await self._fetcher.fetch(url)
            except WebFetchError as exc:
                if exc.kind not in FALLBACK_KINDS or self._extractor is None:
                    logger.info("web page %s failed: kind=%s status=%s", host, exc.kind, exc.status)
                    raise
                logger.info("web page %s local failed (kind=%s status=%s), try tavily", host, exc.kind, exc.status)
                try:
                    page = await self._extractor.extract(url)
                except WebFetchError as fallback_exc:
                    logger.warning(
                        "web page %s tavily failed: kind=%s status=%s %s",
                        host, fallback_exc.kind, fallback_exc.status,
                        fallback_exc.message if fallback_exc.message.startswith("Tavily") else "",
                    )
                    # 给用户看本地抓取的原因（更具体）
                    raise exc from None
        self._remember([url, page.url], page)
        logger.info(
            "web page %s ok via=%s chars=%d %.1fs", host, page.via, page.char_count, time.perf_counter() - start
        )
        return page

    async def aclose(self) -> None:
        for obj in (self._fetcher, self._extractor):
            if obj is not None and hasattr(obj, "aclose"):
                await obj.aclose()
