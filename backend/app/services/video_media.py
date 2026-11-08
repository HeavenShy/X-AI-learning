"""视频出题的媒体处理：用 ffmpeg 探测时长 / 音轨、抽音轨并按段切成 mp3。

ffmpeg 来自 pip 包 imageio-ffmpeg 自带的静态可执行文件，部署时不用另外安装。
都是阻塞的子进程调用，调用方放线程池（asyncio.to_thread）。

转写接口（硅基流动 SenseVoice）只返回文本、不带时间戳，所以按 segment_seconds（默认 60 秒）切段逐段转写，
每段的起止时间就是出处里的时间点。16 kHz 单声道 32 kbps mp3 每分钟约 240 KB，远低于接口 50 MB 的上限。
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MESSAGES: dict[str, str] = {
    "not_video": "读不出这个视频：文件可能损坏，或者不是常见的视频格式（mp4、mov 等）。",
    "no_audio": "这个视频没有声音，没法按讲话内容出题。",
    "too_long": "视频超过 {minutes} 分钟了：先剪出想学的一段再上传。",
    "failed": "视频处理失败，请稍后重新上传。",
}

_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_STREAM = re.compile(r"Stream #\d+:\d+[^:]*: Audio:")
PROBE_TIMEOUT_SECONDS = 30


class MediaError(Exception):
    def __init__(self, kind: str, message: str | None = None):
        super().__init__(message or MESSAGES.get(kind, MESSAGES["failed"]))
        self.kind = kind
        self.message = str(self)


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    has_audio: bool


@dataclass(frozen=True)
class AudioSegment:
    start: float
    end: float
    path: Path


@dataclass(frozen=True)
class TimedText:
    """一段带时间的文字（转写的一段音频，或一条字幕）。"""

    start: float
    end: float
    text: str


def ffmpeg_exe() -> str:
    import imageio_ffmpeg  # 延迟导入：不用视频功能时不加载

    return imageio_ffmpeg.get_ffmpeg_exe()


def parse_probe(stderr: str) -> MediaInfo | None:
    """解析 `ffmpeg -i` 的输出；读不出时长返回 None。"""
    m = _DURATION.search(stderr)
    if not m:
        return None
    h, mi, s = m.groups()
    return MediaInfo(duration=int(h) * 3600 + int(mi) * 60 + float(s), has_audio=bool(_AUDIO_STREAM.search(stderr)))


def probe(path: Path) -> MediaInfo:
    """探测时长与是否有音轨。读不出来抛 not_video，没有音轨抛 no_audio。"""
    try:
        proc = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-i", str(path)],
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise MediaError("not_video") from None
    info = parse_probe(proc.stderr.decode("utf-8", errors="replace"))
    if info is None or info.duration <= 0:
        raise MediaError("not_video")
    if not info.has_audio:
        raise MediaError("no_audio")
    return info


def extract_segments(path: Path, out_dir: Path, *, duration: float, segment_seconds: int) -> list[AudioSegment]:
    """抽音轨并按 segment_seconds 切成 16 kHz 单声道 mp3。返回按时间排序的段。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "part_%04d.mp3"
    # 转码通常远快于实时，给足余量
    timeout = max(120, int(duration))
    try:
        proc = subprocess.run(
            [
                ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
                "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
                "-f", "segment", "-segment_time", str(segment_seconds), "-reset_timestamps", "1",
                str(pattern),
            ],
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise MediaError("failed") from None
    files = sorted(out_dir.glob("part_*.mp3"))
    if proc.returncode != 0 or not files:
        logger.warning("ffmpeg segment failed: rc=%s files=%d", proc.returncode, len(files))
        raise MediaError("failed")
    segments = []
    for i, f in enumerate(files):
        start = float(i * segment_seconds)
        end = min(float((i + 1) * segment_seconds), duration) if duration > 0 else start + segment_seconds
        segments.append(AudioSegment(start=start, end=max(end, start), path=f))
    return segments
