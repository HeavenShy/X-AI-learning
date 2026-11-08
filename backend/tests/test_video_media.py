"""视频媒体处理（真 ffmpeg）、转写客户端与并发转写、B 站链接解析与字幕。"""

import json
import subprocess
from pathlib import Path

import httpx
import pytest

from app.services.bilibili import (
    MSG_NOT_BILIBILI,
    BilibiliClient,
    BilibiliError,
    canonical_video_url,
    find_bilibili_url,
    parse_subtitle,
)
from app.services.transcriber import (
    SiliconFlowTranscriber,
    TranscribeError,
    clean_transcript,
    transcribe_segments,
)
from app.services.video_media import AudioSegment, MediaError, TimedText, extract_segments, ffmpeg_exe, parse_probe, probe
from tests.llm_mock import test_settings


def make_video(path: Path, *, seconds: int, audio: bool = True) -> Path:
    """lavfi 现场生成测试视频：黑画面 + 正弦音（audio=False 时没有音轨）。"""
    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s=64x48:d={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest", "-c:a", "aac"]
    args += ["-c:v", "libx264", str(path)]
    subprocess.run(args, check=True, capture_output=True, timeout=60)
    return path


# ---------- ffmpeg ----------


def test_parse_probe():
    out = (
        "Input #0, mov,mp4\n  Duration: 00:02:30.50, start: 0.000000, bitrate: 79 kb/s\n"
        "  Stream #0:0[0x1](und): Video: h264\n  Stream #0:1[0x2](und): Audio: aac (LC)\n"
    )
    info = parse_probe(out)
    assert info.duration == 150.5 and info.has_audio
    assert parse_probe("Invalid data found when processing input") is None
    assert parse_probe("  Duration: 00:00:05.00, start\n  Stream #0:0: Video: h264").has_audio is False


def test_probe_and_segment_real_video(tmp_path):
    video = make_video(tmp_path / "a.mp4", seconds=5)
    info = probe(video)
    assert 4.5 < info.duration < 5.5 and info.has_audio
    segs = extract_segments(video, tmp_path / "seg", duration=info.duration, segment_seconds=2)
    assert [(s.start, round(s.end)) for s in segs] == [(0.0, 2), (2.0, 4), (4.0, 5)]
    assert all(s.path.exists() and s.path.suffix == ".mp3" for s in segs)


def test_probe_rejects_silent_and_broken(tmp_path):
    with pytest.raises(MediaError) as e:
        probe(make_video(tmp_path / "silent.mp4", seconds=2, audio=False))
    assert e.value.kind == "no_audio"
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video at all")
    with pytest.raises(MediaError) as e:
        probe(bad)
    assert e.value.kind == "not_video"


# ---------- 转写 ----------


def transcriber(handler) -> SiliconFlowTranscriber:
    s = test_settings(siliconflow_api_key="sk-sf")
    return SiliconFlowTranscriber(s, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_clean_transcript():
    assert clean_transcript("<|zh|><|NEUTRAL|><|Speech|>复利就是利滚利。") == "复利就是利滚利。"


async def test_transcribe_request_and_tags(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        return httpx.Response(200, json={"text": "<|zh|>大家好，今天讲复利。"})

    f = tmp_path / "part_0000.mp3"
    f.write_bytes(b"ID3fake")
    text = await transcriber(handler).transcribe(f)
    assert text == "大家好,今天讲复利。"  # clean_text 规范了全角逗号
    assert seen["path"].endswith("/audio/transcriptions")
    assert seen["auth"] == "Bearer sk-sf"
    assert b"FunAudioLLM/SenseVoiceSmall" in seen["body"] and b"ID3fake" in seen["body"]


async def test_transcribe_retries_429_then_ok(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.transcriber.RETRY_DELAY_SECONDS", 0)
    statuses = iter([429, 200])

    def handler(request):
        code = next(statuses)
        return httpx.Response(code, json={"text": "好"} if code == 200 else {})

    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    assert await transcriber(handler).transcribe(f) == "好"


async def test_transcribe_400_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.transcriber.RETRY_DELAY_SECONDS", 0)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, text="bad")

    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    with pytest.raises(TranscribeError) as e:
        await transcriber(handler).transcribe(f)
    assert e.value.status == 400 and len(calls) == 1


class FakeTranscriber:
    def __init__(self, texts: dict[str, str | Exception]):
        self.texts = texts

    async def transcribe(self, path: Path) -> str:
        v = self.texts[path.name]
        if isinstance(v, Exception):
            raise v
        return v


def segs(n: int) -> list[AudioSegment]:
    return [AudioSegment(i * 60.0, (i + 1) * 60.0, Path(f"p{i}.mp3")) for i in range(n)]


async def test_transcribe_segments_orders_and_reports_progress():
    progress = []
    t = FakeTranscriber({"p0.mp3": "第一段", "p1.mp3": "", "p2.mp3": "第三段"})
    out = await transcribe_segments(t, segs(3), concurrency=2, on_progress=progress.append)
    assert out == [TimedText(0.0, 60.0, "第一段"), TimedText(120.0, 180.0, "第三段")]
    assert sorted(progress) == [1, 2, 3]


async def test_transcribe_segments_tolerates_few_failures():
    texts = {f"p{i}.mp3": f"第{i}段" for i in range(5)}
    texts["p2.mp3"] = TranscribeError("x", status=503)
    out = await transcribe_segments(FakeTranscriber(texts), segs(5), concurrency=3)
    assert len(out) == 4
    texts["p3.mp3"] = TranscribeError("x", status=503)
    with pytest.raises(TranscribeError):
        await transcribe_segments(FakeTranscriber(texts), segs(5), concurrency=3)


# ---------- B 站 ----------


@pytest.mark.parametrize(
    "text,url",
    [
        ("【两分钟告诉你什么是复利？】 https://www.bilibili.com/video/BV1ns411w7tt/?share_source=copy", "https://www.bilibili.com/video/BV1ns411w7tt/?share_source=copy"),
        ("https://b23.tv/AbCdEf 复制此链接", "https://b23.tv/AbCdEf"),
        (" BV1ns411w7tt ", "https://www.bilibili.com/video/BV1ns411w7tt"),
        ("https://www.youtube.com/watch?v=x", None),
        ("https://evilbilibili.com/video/BV1ns411w7tt", None),
        ("什么是复利", None),
    ],
)
def test_find_bilibili_url(text, url):
    assert find_bilibili_url(text) == url


def test_canonical_video_url():
    assert canonical_video_url("https://m.bilibili.com/video/BV1ns411w7tt?spm=1") == "https://www.bilibili.com/video/BV1ns411w7tt"
    assert canonical_video_url("https://www.bilibili.com/video/av25762973/?p=2") == "https://www.bilibili.com/video/av25762973?p=2"
    assert canonical_video_url("https://www.bilibili.com/read/cv123") is None
    assert canonical_video_url("https://space.bilibili.com/123") is None


def test_parse_subtitle_json_and_srt():
    data = json.dumps({"body": [{"from": 0.5, "to": 2.0, "content": "大家好"}, {"from": 2.0, "to": 4, "content": " "}]})
    assert parse_subtitle(data.encode(), "json") == [TimedText(0.5, 2.0, "大家好")]
    srt = "1\n00:00:01,000 --> 00:00:03,500\n复利就是\n利滚利\n\n2\n00:01:05,000 --> 00:01:07,000\n下一句\n"
    assert parse_subtitle(srt.encode(), "srt") == [TimedText(1.0, 3.5, "复利就是 利滚利"), TimedText(65.0, 67.0, "下一句")]


class FakeYdl:
    """记录选项；info / download 的行为由 FakeYdl.script 决定。"""

    script: dict = {}
    created: list[dict] = []

    def __init__(self, opts):
        self.opts = opts
        FakeYdl.created.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        v = FakeYdl.script["info"]
        if isinstance(v, Exception):
            raise v
        return v

    def urlopen(self, url):
        class R:
            def read(_self):
                return FakeYdl.script["sub"]

        return R()

    def download(self, urls):
        v = FakeYdl.script.get("download")
        if isinstance(v, Exception):
            raise v
        out = Path(self.opts["outtmpl"].replace("%(ext)s", "m4a"))
        out.write_bytes(b"audio")


def bili(handler=None, **settings_kw) -> BilibiliClient:
    FakeYdl.created = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler or (lambda r: httpx.Response(404))))
    return BilibiliClient(test_settings(**settings_kw), ydl_factory=FakeYdl, http_client=http)


async def test_resolve_short_link_one_hop_and_validate():
    def handler(request):
        assert request.url.host == "b23.tv"
        return httpx.Response(302, headers={"location": "https://m.bilibili.com/video/BV1ns411w7tt?share=1"})

    assert await bili(handler).resolve("看这个 https://b23.tv/xyz") == "https://www.bilibili.com/video/BV1ns411w7tt"

    def evil(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    with pytest.raises(BilibiliError) as e:
        await bili(evil).resolve("https://b23.tv/xyz")
    assert e.value.kind == "invalid"


async def test_resolve_rejects_other_sites():
    with pytest.raises(BilibiliError) as e:
        await bili().resolve("https://v.qq.com/x/abc.html")
    assert e.value.message == MSG_NOT_BILIBILI


async def test_info_uses_only_bilibili_extractor_and_skips_danmaku():
    FakeYdl.script = {"info": {"id": "BV1ns411w7tt", "title": "两分钟  讲复利", "duration": 139.5,
                               "subtitles": {"danmaku": [{"ext": "xml"}], "zh-Hans": [{"ext": "json", "url": "u"}]}}}
    c = bili()
    info = await c.info("https://www.bilibili.com/video/BV1ns411w7tt")
    assert (info.title, info.duration, list(info.subtitles)) == ("两分钟 讲复利", 139.5, ["zh-Hans"])
    assert FakeYdl.created[0]["allowed_extractors"] == ["BiliBili"] and FakeYdl.created[0]["noplaylist"]
    FakeYdl.script["sub"] = json.dumps({"body": [{"from": 0, "to": 3, "content": "复利就是利滚利"}]}).encode()
    assert await c.subtitles(info) == [TimedText(0, 3, "复利就是利滚利")]


async def test_info_failure_becomes_friendly_error():
    FakeYdl.script = {"info": RuntimeError("412 Precondition Failed")}
    with pytest.raises(BilibiliError) as e:
        await bili().info("https://www.bilibili.com/video/BV1ns411w7tt")
    assert "可以把视频保存到手机后上传" in e.value.message


async def test_download_audio(tmp_path):
    FakeYdl.script = {"download": None}
    path = await bili().download_audio("https://www.bilibili.com/video/BV1ns411w7tt", tmp_path / "dl")
    assert path.name == "audio.m4a" and path.read_bytes() == b"audio"
    FakeYdl.script = {"download": RuntimeError("blocked")}
    with pytest.raises(BilibiliError):
        await bili().download_audio("https://www.bilibili.com/video/BV1ns411w7tt", tmp_path / "dl2")
