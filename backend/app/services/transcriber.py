"""语音转写：硅基流动 POST {SILICONFLOW_BASE_URL}/audio/transcriptions（multipart：model、file）。

模型默认 FunAudioLLM/SenseVoiceSmall；响应只有 text（没有时间戳），所以调用方按段转写。
单个文件上限 1 小时 / 50 MB，按 60 秒切段远低于上限。
429 / 5xx / 网络错误重试 1 次；日志和异常只记状态码，不记 Key 和音频内容。
"""

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import Settings
from app.services.video_media import AudioSegment, TimedText
from app.utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)

# SenseVoice 原始输出可能带 <|zh|><|NEUTRAL|><|Speech|> 一类标签
_TAGS = re.compile(r"<\|[^|>]*\|>")
RETRY_DELAY_SECONDS = 1.0
# 失败段数超过总段数的这个比例，整体判为失败
MAX_FAILED_RATIO = 0.2


class TranscribeError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Transcriber(Protocol):
    async def transcribe(self, path: Path) -> str: ...


def clean_transcript(text: str) -> str:
    return clean_text(_TAGS.sub("", text or ""))


class SiliconFlowTranscriber:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http = http_client or httpx.AsyncClient(timeout=settings.asr_timeout_seconds)

    async def transcribe(self, path: Path) -> str:
        s = self._settings
        data = await asyncio.to_thread(path.read_bytes)
        last: TranscribeError | None = None
        for attempt in range(2):
            if attempt:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            try:
                resp = await self._http.post(
                    f"{s.siliconflow_base_url.rstrip('/')}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {s.siliconflow_api_key}"},
                    data={"model": s.asr_model},
                    files={"file": (path.name, data, "audio/mpeg")},
                    timeout=s.asr_timeout_seconds,
                )
            except httpx.HTTPError as exc:
                # 只保留异常类型：httpx 的异常对象会挂着带 Authorization 头的 request
                last = TranscribeError(f"转写网络错误（{type(exc).__name__}）")
                continue
            if resp.status_code == 200:
                try:
                    body = resp.json()
                except ValueError:
                    raise TranscribeError("转写返回非 JSON", status=200) from None
                return clean_transcript(str(body.get("text") or "") if isinstance(body, dict) else "")
            last = TranscribeError(f"转写 HTTP {resp.status_code}", status=resp.status_code)
            if resp.status_code != 429 and resp.status_code < 500:
                break
        raise last or TranscribeError("转写失败")

    async def aclose(self) -> None:
        await self._http.aclose()


async def transcribe_segments(
    transcriber: Transcriber,
    segments: Sequence[AudioSegment],
    *,
    concurrency: int,
    on_progress: Callable[[int], None] | None = None,
) -> list[TimedText]:
    """并发转写各段，按时间排序返回（空文本的段去掉）。失败段超过 1/5 抛 TranscribeError。"""
    sem = asyncio.Semaphore(max(1, concurrency))
    done = 0
    failed: list[TranscribeError] = []

    async def one(seg: AudioSegment) -> TimedText | None:
        nonlocal done
        async with sem:
            try:
                text = await transcriber.transcribe(seg.path)
            except TranscribeError as exc:
                failed.append(exc)
                text = ""
            done += 1
            if on_progress:
                on_progress(done)
        return TimedText(start=seg.start, end=seg.end, text=text) if text else None

    results = await asyncio.gather(*(one(s) for s in segments))
    if failed and len(failed) > max(0, int(len(segments) * MAX_FAILED_RATIO)):
        statuses = sorted({e.status for e in failed if e.status is not None})
        logger.warning("transcribe failed: %d/%d segments, statuses=%s", len(failed), len(segments), statuses)
        raise TranscribeError(f"{len(failed)}/{len(segments)} 段转写失败", status=statuses[0] if statuses else None)
    return [r for r in results if r is not None]
