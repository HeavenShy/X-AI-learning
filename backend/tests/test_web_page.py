"""网页抓取：URL 规范化、SSRF 防护、重定向、大小 / 类型限制、正文提取、Tavily 兜底与缓存。"""

import json

import httpx
import pytest

from app.services.web_page import (
    MESSAGES,
    LocalPageFetcher,
    PageReader,
    TavilyExtractor,
    WebFetchError,
    WebPage,
    is_public_ip,
    normalize_url,
)
from app.utils.text_cleaner import clean_text
from tests.llm_mock import test_settings

PUBLIC_IP = "93.184.216.34"

PARAGRAPH = "检索增强生成（RAG）先从知识库里检索和问题相关的片段，再把片段连同问题一起交给大模型生成回答，这样能减少幻觉、用上最新资料。"

ARTICLE_HTML = (
    "<html><head><title>一文看懂 RAG - 某博客</title>"
    '<meta property="og:title" content="一文看懂 RAG"><meta property="og:site_name" content="某博客"></head>'
    "<body><nav>首页 | 关于 | 登录 | 注册</nav><article><h1>一文看懂 RAG</h1>"
    + "".join(f"<p>第{i}段：{PARAGRAPH}</p>" for i in range(6))
    + "</article><footer>版权所有 © 2026 某博客 联系我们</footer></body></html>"
)


def settings(**kw):
    base = dict(web_page_min_chars=100, web_fetch_max_bytes=200_000, tavily_api_key="tvly-test")
    base.update(kw)
    return test_settings(**base)


def resolver(mapping: dict[str, list[str]] | None = None, default: list[str] | None = None):
    calls: list[str] = []

    async def resolve(host: str, port: int) -> list[str]:
        calls.append(host)
        if mapping and host in mapping:
            return mapping[host]
        if default is None:
            raise OSError("no such host")
        return default

    resolve.calls = calls  # type: ignore[attr-defined]
    return resolve


class Site:
    """按路径返回预设响应，记录请求。"""

    def __init__(self, routes: dict):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.url.host}{request.url.path}"
        r = self.routes.get(key)
        if r is None:
            return httpx.Response(404)
        return r(request) if callable(r) else r

    def fetcher(self, s=None, resolve=None) -> LocalPageFetcher:
        s = s or settings()
        return LocalPageFetcher(
            s,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self._handle)),
            resolve=resolve or resolver(default=[PUBLIC_IP]),
        )


def html(body: str = ARTICLE_HTML, **headers) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8", **headers}, content=body.encode())


# ---------- URL 规范化与地址校验 ----------


def test_normalize_adds_scheme_and_drops_fragment():
    assert normalize_url("  mp.weixin.qq.com/s/abc#x ") == "https://mp.weixin.qq.com/s/abc"
    assert normalize_url("http://example.com/a?b=1") == "http://example.com/a?b=1"


@pytest.mark.parametrize(
    "raw,kind",
    [
        ("", "invalid_url"),
        ("不是网址", "invalid_url"),
        ("https://exa mple.com", "invalid_url"),
        ("ftp://example.com/a", "invalid_url"),
        ("javascript:alert(1)", "invalid_url"),
        ("http://localhost/admin", "invalid_url"),
        ("http://user:pw@example.com/", "invalid_url"),
        ("http://example.com:8080/", "blocked_address"),
    ],
)
def test_normalize_rejects(raw, kind):
    with pytest.raises(WebFetchError) as e:
        normalize_url(raw)
    assert e.value.kind == kind


@pytest.mark.parametrize(
    "ip,public",
    [
        (PUBLIC_IP, True),
        ("8.8.8.8", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("::1", False),
        ("fc00::1", False),
        ("fe80::1%eth0", False),
        ("::ffff:127.0.0.1", False),
        ("224.0.0.1", False),
        ("2606:4700::1111", True),
    ],
)
def test_is_public_ip(ip, public):
    assert is_public_ip(ip) is public


# ---------- 本地抓取 ----------


async def test_fetch_extracts_article_without_nav_and_footer():
    site = Site({"blog.example.com/rag": html()})
    page = await site.fetcher().fetch("https://blog.example.com/rag")
    assert page.via == "local"
    assert page.site == "blog.example.com"
    assert page.title == "一文看懂 RAG"
    assert "检索增强生成" in page.text
    assert "版权所有" not in page.text and "注册" not in page.text
    assert page.char_count > 200
    # 带浏览器 UA，不带用户信息
    assert "Mozilla/5.0" in site.requests[0].headers["user-agent"]


async def test_host_resolving_to_private_ip_is_blocked_before_request():
    site = Site({"intranet.example.com/": html()})
    resolve = resolver({"intranet.example.com": ["10.0.0.8"]})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher(resolve=resolve).fetch("https://intranet.example.com/")
    assert e.value.kind == "blocked_address"
    assert site.requests == []


async def test_any_private_address_in_dns_answer_is_blocked():
    site = Site({"mixed.example.com/": html()})
    resolve = resolver({"mixed.example.com": [PUBLIC_IP, "127.0.0.1"]})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher(resolve=resolve).fetch("https://mixed.example.com/")
    assert e.value.kind == "blocked_address"


async def test_metadata_ip_literal_is_blocked():
    site = Site({})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher().fetch("http://169.254.169.254/latest/meta-data/")
    assert e.value.kind == "blocked_address"
    assert site.requests == []


async def test_unresolvable_host_is_unreachable():
    site = Site({})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher(resolve=resolver()).fetch("https://nope.example.com/")
    assert e.value.kind == "unreachable"


async def test_redirect_is_followed_and_rechecked():
    site = Site(
        {
            "short.example.com/x": httpx.Response(302, headers={"location": "https://blog.example.com/rag"}),
            "blog.example.com/rag": html(),
        }
    )
    page = await site.fetcher().fetch("https://short.example.com/x")
    assert page.url == "https://blog.example.com/rag"
    assert len(site.requests) == 2


async def test_redirect_to_internal_address_is_blocked():
    site = Site({"evil.example.com/x": httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher().fetch("https://evil.example.com/x")
    assert e.value.kind == "blocked_address"
    assert len(site.requests) == 1


async def test_redirect_to_other_port_is_blocked():
    site = Site({"evil.example.com/x": httpx.Response(301, headers={"location": "http://example.com:6379/"})})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher().fetch("https://evil.example.com/x")
    assert e.value.kind == "blocked_address"


async def test_too_many_redirects():
    site = Site({"loop.example.com/a": httpx.Response(302, headers={"location": "/a"})})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher(settings(web_fetch_max_redirects=3)).fetch("https://loop.example.com/a")
    assert e.value.kind == "unreachable"
    assert "跳转次数太多" in e.value.message
    assert len(site.requests) == 4


async def test_declared_content_length_over_limit():
    site = Site({"big.example.com/": html(ARTICLE_HTML, **{"content-length": "999999"})})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher(settings(web_fetch_max_bytes=1000)).fetch("https://big.example.com/")
    assert e.value.kind == "too_large"


class _Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def __aiter__(self):
        for c in self._chunks:
            yield c


async def test_streamed_body_over_limit_without_content_length():
    resp = httpx.Response(200, headers={"content-type": "text/html"}, stream=_Chunks([b"<html>" + b"x" * 600] * 3))
    site = Site({"big.example.com/": resp})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher(settings(web_fetch_max_bytes=1000)).fetch("https://big.example.com/")
    assert e.value.kind == "too_large"


async def test_pdf_link_points_to_knowledge_base():
    site = Site({"x.example.com/a.pdf": httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-")})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher().fetch("https://x.example.com/a.pdf")
    assert e.value.kind == "not_html"
    assert e.value.message == MESSAGES["not_html_pdf"]


async def test_image_is_not_supported():
    site = Site({"x.example.com/a.png": httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG")})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher().fetch("https://x.example.com/a.png")
    assert e.value.kind == "not_html"


@pytest.mark.parametrize("status,kind", [(403, "http_blocked"), (401, "http_blocked"), (502, "http_blocked"), (404, "not_found"), (418, "unreachable")])
async def test_http_status_kinds(status, kind):
    site = Site({"x.example.com/": httpx.Response(status)})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher().fetch("https://x.example.com/")
    assert e.value.kind == kind
    assert e.value.status == status


async def test_page_without_article_is_no_text():
    site = Site({"x.example.com/": html("<html><body><div id='app'></div><script>render()</script></body></html>")})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher().fetch("https://x.example.com/")
    assert e.value.kind == "no_text"


async def test_plain_text_page():
    body = "复利怎么算\n\n" + PARAGRAPH * 3
    site = Site({"x.example.com/a.txt": httpx.Response(200, headers={"content-type": "text/plain"}, content=body.encode())})
    page = await site.fetcher().fetch("https://x.example.com/a.txt")
    assert page.title == "复利怎么算"
    # 正文统一清洗过（全角标点 NFKC 规范化）
    assert clean_text(PARAGRAPH) in page.text


async def test_text_over_max_chars_is_truncated():
    site = Site({"x.example.com/": html()})
    page = await site.fetcher(settings(web_page_max_chars=300)).fetch("https://x.example.com/")
    assert len(page.text) <= 300


async def test_network_error_is_unreachable():
    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    site = Site({"x.example.com/": boom})
    with pytest.raises(WebFetchError) as e:
        await site.fetcher().fetch("https://x.example.com/")
    assert e.value.kind == "unreachable"


# ---------- Tavily 兜底与缓存 ----------


def tavily(results=None, status: int = 200):
    calls: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append({"path": request.url.path, "body": json.loads(request.content), "auth": request.headers["authorization"]})
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json={"results": results or [], "failed_results": []})

    s = settings()
    ex = TavilyExtractor(s, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    return ex, calls


class FakeFetcher:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    async def fetch(self, url: str) -> WebPage:
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def page(url="https://blog.example.com/rag") -> WebPage:
    return WebPage(url=url, site="blog.example.com", title="一文看懂 RAG", text=PARAGRAPH * 3, char_count=180, via="local")


async def test_no_text_falls_back_to_tavily():
    ex, calls = tavily([{"url": "https://spa.example.com/a", "raw_content": "动态页面的标题\n" + PARAGRAPH * 3}])
    reader = PageReader(settings(), fetcher=FakeFetcher(WebFetchError("no_text")), extractor=ex)
    result = await reader.read("https://spa.example.com/a")
    assert result.via == "tavily"
    assert result.title == "动态页面的标题"
    assert calls[0]["path"] == "/extract"
    assert calls[0]["body"] == {"urls": ["https://spa.example.com/a"], "extract_depth": "basic", "format": "text"}
    assert calls[0]["auth"] == "Bearer tvly-test"


@pytest.mark.parametrize("kind", ["blocked_address", "not_html", "too_large"])
async def test_no_fallback_for_unfixable_errors(kind):
    ex, calls = tavily([{"raw_content": PARAGRAPH * 3}])
    reader = PageReader(settings(), fetcher=FakeFetcher(WebFetchError(kind)), extractor=ex)
    with pytest.raises(WebFetchError) as e:
        await reader.read("https://x.example.com/")
    assert e.value.kind == kind
    assert calls == []


async def test_invalid_url_never_reaches_fetcher():
    fetcher = FakeFetcher(page())
    reader = PageReader(settings(), fetcher=fetcher)
    with pytest.raises(WebFetchError):
        await reader.read("ftp://x.example.com/")
    assert fetcher.calls == 0


async def test_tavily_failure_reports_local_reason():
    ex, _ = tavily(status=432)
    reader = PageReader(settings(), fetcher=FakeFetcher(WebFetchError("http_blocked", status=403)), extractor=ex)
    with pytest.raises(WebFetchError) as e:
        await reader.read("https://x.example.com/")
    assert e.value.kind == "http_blocked"
    assert e.value.message == MESSAGES["http_blocked"]


async def test_tavily_short_content_is_no_text():
    ex, _ = tavily([{"raw_content": "太短"}])
    reader = PageReader(settings(), fetcher=FakeFetcher(WebFetchError("no_text")), extractor=ex)
    with pytest.raises(WebFetchError) as e:
        await reader.read("https://x.example.com/")
    assert e.value.kind == "no_text"


async def test_without_extractor_error_propagates():
    reader = PageReader(settings(), fetcher=FakeFetcher(WebFetchError("no_text")), extractor=None)
    with pytest.raises(WebFetchError) as e:
        await reader.read("https://x.example.com/")
    assert e.value.kind == "no_text"


async def test_cache_hit_and_expiry():
    now = [1000.0]
    fetcher = FakeFetcher(page())
    reader = PageReader(settings(web_page_cache_seconds=600), fetcher=fetcher, clock=lambda: now[0])
    await reader.read("blog.example.com/rag")
    await reader.read("https://blog.example.com/rag#top")
    assert fetcher.calls == 1
    now[0] += 601
    await reader.read("https://blog.example.com/rag")
    assert fetcher.calls == 2


async def test_cache_is_bounded():
    fetcher = FakeFetcher(page())
    reader = PageReader(settings(), fetcher=fetcher, cache_size=2)
    for i in range(3):
        await reader.read(f"https://blog.example.com/{i}")
    await reader.read("https://blog.example.com/0")
    assert fetcher.calls == 4
