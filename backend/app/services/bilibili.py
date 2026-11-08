"""B 站链接：解析链接 → yt-dlp 取视频信息 → 有中文 CC 字幕用字幕，否则下载音频（再交给 ffmpeg 切段转写）。

尽力而为：B 站有风控，AI 字幕和部分视频需要登录，会员 / 地区限制的视频读不了。任何失败都转成 BilibiliError，
提示用户把视频保存到手机后上传。

安全：只接受 bilibili.com / m.bilibili.com / b23.tv 的链接（也可以只给 BV 号），统一规范成
https://www.bilibili.com/video/<BV 或 av 号>；b23.tv 短链自己解析一跳（不跟随，读 Location 后再校验）。
yt-dlp 只开 BiliBili 一个 extractor，不会被引到别的站点。日志只记视频号和异常类型。
"""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core.config import Settings
from app.services.video_media import TimedText
from app.utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)

MSG_NOT_BILIBILI = "只支持 B 站视频链接（bilibili.com 或 b23.tv），其他视频可以保存到手机后上传。"
MSG_UNAVAILABLE = "这个 B 站视频读不了（可能要登录、有地区或版权限制）。可以把视频保存到手机后上传。"

_URL = re.compile(r"https?://[^\s<>\"'，。！？、；：（）【】《》「」]+", re.I)
_VIDEO_ID = re.compile(r"(BV[0-9A-Za-z]{10}|av\d+)", re.I)
_BV_ONLY = re.compile(r"^\s*(BV[0-9A-Za-z]{10})\s*$")
_HOSTS = ("bilibili.com", "b23.tv")
# 字幕语言优先级（UP 主上传的 CC 字幕；ai-zh 需要登录，拿到了也用）
_SUB_LANGS = ("zh-Hans", "zh-CN", "zh", "zh-Hant", "ai-zh")


class BilibiliError(Exception):
    def __init__(self, message: str = MSG_UNAVAILABLE, *, kind: str = "unavailable"):
        super().__init__(message)
        self.message = message
        self.kind = kind


def _host_ok(host: str) -> bool:
    host = host.lower()
    return any(host == h or host.endswith("." + h) for h in _HOSTS)


def find_bilibili_url(text: str) -> str | None:
    """从分享文案里取 B 站链接或 BV 号；没有返回 None。只看 host，不联网。"""
    m = _BV_ONLY.match(text or "")
    if m:
        return f"https://www.bilibili.com/video/{m.group(1)}"
    for raw in _URL.findall(text or ""):
        url = raw.rstrip(".,;:!?)]}")
        try:
            host = httpx.URL(url).host
        except Exception:  # noqa: BLE001
            continue
        if host and _host_ok(host):
            return url
    return None


def canonical_video_url(url: str) -> str | None:
    """bilibili.com 的视频链接 → https://www.bilibili.com/video/<id>（保留分 P 参数）；不是视频链接返回 None。"""
    try:
        u = httpx.URL(url)
    except Exception:  # noqa: BLE001
        return None
    if not u.host or not u.host.lower().endswith("bilibili.com"):
        return None
    m = _VIDEO_ID.search(u.path)
    if not m:
        return None
    vid = m.group(1)
    vid = "BV" + vid[2:] if vid[:2].lower() == "bv" else vid.lower()
    page = u.params.get("p")
    return f"https://www.bilibili.com/video/{vid}" + (f"?p={page}" if page and page.isdigit() else "")


def parse_subtitle(data: bytes, ext: str) -> list[TimedText]:
    """B 站 json 字幕（{"body":[{"from","to","content"}]}）或 srt → 带时间的文字。"""
    text = data.decode("utf-8", errors="replace")
    items: list[TimedText] = []
    if ext == "json" or text.lstrip().startswith("{"):
        try:
            body = json.loads(text).get("body") or []
        except (ValueError, AttributeError):
            return []
        for it in body:
            if isinstance(it, dict) and str(it.get("content") or "").strip():
                items.append(TimedText(float(it.get("from") or 0), float(it.get("to") or 0), str(it["content"])))
        return items
    # srt：序号 / 时间行 / 文本，空行分隔
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", block)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        content = " ".join(line for line in block[m.end():].split("\n") if line.strip())
        if content.strip():
            items.append(TimedText(start, end, content))
    return items


@dataclass
class BiliInfo:
    video_id: str
    title: str
    duration: float
    url: str
    # 语言 → [{ext, url}]
    subtitles: dict = field(default_factory=dict)


YdlFactory = Callable[[dict], object]


class _YdlLogger:
    """yt-dlp 的输出（含 ERROR）不直接打到 stderr，统一记 debug；失败原因由调用方按异常类型记一条。"""

    def debug(self, msg: str) -> None:
        logger.debug("yt-dlp: %s", msg)

    info = debug
    warning = debug
    error = debug


def _default_ydl(opts: dict):
    import yt_dlp  # 延迟导入

    return yt_dlp.YoutubeDL(opts)


class BilibiliClient:
    def __init__(
        self,
        settings: Settings,
        *,
        ydl_factory: YdlFactory = _default_ydl,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._settings = settings
        self._ydl = ydl_factory
        self._http = http_client or httpx.AsyncClient(follow_redirects=False, timeout=10)

    def _opts(self, **extra) -> dict:
        return {
            "quiet": True,
            "no_warnings": True,
            "logger": _YdlLogger(),
            "noplaylist": True,
            "allowed_extractors": ["BiliBili"],
            "socket_timeout": 20,
            "retries": 1,
            "noprogress": True,
            **extra,
        }

    async def resolve(self, raw: str) -> str:
        """分享文案 / 链接 / BV 号 → 规范的视频链接；不是 B 站视频抛 BilibiliError(kind=invalid)。"""
        url = find_bilibili_url(raw)
        if url is None:
            raise BilibiliError(MSG_NOT_BILIBILI, kind="invalid")
        if httpx.URL(url).host.lower().endswith("b23.tv"):
            try:
                resp = await self._http.get(url, headers={"User-Agent": "Mozilla/5.0"})
            except httpx.HTTPError:
                raise BilibiliError() from None
            location = resp.headers.get("location", "")
            url = str(httpx.URL(url).join(location)) if location else ""
        canonical = canonical_video_url(url)
        if canonical is None:
            raise BilibiliError(MSG_NOT_BILIBILI, kind="invalid")
        return canonical

    def _extract(self, url: str) -> dict:
        ydl = self._ydl(self._opts(skip_download=True))
        with ydl:  # type: ignore[attr-defined]
            return ydl.extract_info(url, download=False)  # type: ignore[attr-defined]

    async def info(self, url: str) -> BiliInfo:
        try:
            data = await asyncio.wait_for(asyncio.to_thread(self._extract, url), timeout=60)
        except Exception as exc:  # noqa: BLE001 —— yt-dlp 的各种错误、超时
            logger.info("bilibili info %s failed: %s", url.rsplit("/", 1)[-1], type(exc).__name__)
            raise BilibiliError() from None
        if not isinstance(data, dict) or not data.get("duration"):
            raise BilibiliError()
        subs = {k: v for k, v in (data.get("subtitles") or {}).items() if k != "danmaku"}
        return BiliInfo(
            video_id=str(data.get("id") or ""),
            title=" ".join(str(data.get("title") or "").split())[:80] or "B 站视频",
            duration=float(data["duration"]),
            url=url,
            subtitles=subs,
        )

    def _read_url(self, url: str) -> bytes:
        ydl = self._ydl(self._opts())
        with ydl:  # type: ignore[attr-defined]
            return ydl.urlopen(url).read()  # type: ignore[attr-defined]

    async def subtitles(self, info: BiliInfo) -> list[TimedText]:
        """有中文字幕时下载并解析；没有或失败返回空列表（调用方改为下载音频转写）。"""
        for lang in _SUB_LANGS:
            for fmt in info.subtitles.get(lang) or []:
                ext, sub_url = str(fmt.get("ext") or ""), str(fmt.get("url") or "")
                if ext not in ("json", "srt") or not sub_url:
                    continue
                try:
                    data = await asyncio.wait_for(asyncio.to_thread(self._read_url, sub_url), timeout=30)
                except Exception as exc:  # noqa: BLE001
                    logger.info("bilibili subtitle %s failed: %s", info.video_id, type(exc).__name__)
                    continue
                # 不合并：每行字幕保留自己的时间，出处能精确到那一句（出题时再按字数拼块）
                items = [TimedText(i.start, i.end, clean_text(i.text)) for i in parse_subtitle(data, ext)]
                items = [i for i in items if i.text]
                if items:
                    return items
        return []

    def _download(self, url: str, out_dir: Path) -> Path:
        opts = self._opts(
            format="bestaudio[abr<=96]/bestaudio/best",
            outtmpl=str(out_dir / "audio.%(ext)s"),
        )
        ydl = self._ydl(opts)
        with ydl:  # type: ignore[attr-defined]
            ydl.download([url])  # type: ignore[attr-defined]
        files = [f for f in out_dir.glob("audio.*") if f.suffix not in (".part", ".ytdl")]
        if not files:
            raise FileNotFoundError("audio not downloaded")
        return files[0]

    async def download_audio(self, url: str, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._download, url, out_dir), timeout=self._settings.bilibili_timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("bilibili download %s failed: %s", url.rsplit("/", 1)[-1], type(exc).__name__)
            raise BilibiliError() from None

    async def aclose(self) -> None:
        await self._http.aclose()
