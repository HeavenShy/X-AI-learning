"""视频出题真模型冒烟：解析（ffmpeg 切段 + 转写 / B 站）→ AI 判断范围 → 出题，核对出处时间点。

用法（在 backend 目录；需要 DEEPSEEK_API_KEY，真转写需要 SILICONFLOW_API_KEY 且账户有余额）：
    python -m scripts.smoke_video --video 讲解.mp4 [--video ...] [-n 2] [--focus "..."] [--range 60-180] [--show]
    python -m scripts.smoke_video --bilibili https://www.bilibili.com/video/BV... [--show]
    python -m scripts.smoke_video --video 讲解.mp4 --fake-asr 讲稿.json      # 转写用讲稿替身（见下）

--fake-asr：讲稿 JSON 是 [{"section", "start", "end", "text"}, ...]（秒）。转写替身按每段音频的起止时间，
从讲稿里按字数比例截出这段时间“讲”的文字，其余（ffmpeg 切段、范围判断、出题、出处）都是真的。
用于转写服务不可用时验证出题与时间点；这时“出处时间点落在讲稿哪一节”可以精确核对。

每次打印：解析耗时、段数、字数；范围判断结果与知识点；出题耗时、尝试次数；每题出处的时间点、
摘录在文字稿里能否找到、（有讲稿时）时间点是否落在摘录所在的那一节。题目不落库。
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from app.api.deps import get_web_quiz_generator, get_web_scope_judge
from app.core.config import get_settings
from app.core.exceptions import BizError
from app.core.logging import setup_logging
from app.models.video import VideoQuizRequest
from app.services.bilibili import BilibiliClient
from app.services.material_quiz import format_clock
from app.services.transcriber import SiliconFlowTranscriber
from app.services.video_jobs import VideoJob, VideoJobManager
from app.services.video_quiz_service import VideoQuizService
from app.utils.content_filter import get_content_filter

SMOKE_USER = 4_000_000_002


def _squash(text: str) -> str:
    from app.utils.text_cleaner import clean_text

    return "".join(clean_text(text).split())


class TimelineTranscriber:
    """转写替身：按音频段的起止时间，从讲稿里按字数比例截出那段时间讲的文字。"""

    def __init__(self, timeline: list[dict], segment_seconds: int):
        self.timeline = timeline
        self.segment_seconds = segment_seconds

    async def transcribe(self, path: Path) -> str:
        idx = int(path.stem.rsplit("_", 1)[-1])
        lo, hi = idx * self.segment_seconds, (idx + 1) * self.segment_seconds
        parts = []
        for sec in self.timeline:
            s, e, text = float(sec["start"]), float(sec["end"]), sec["text"]
            if e <= lo or s >= hi or e <= s:
                continue
            a = int(len(text) * max(0.0, lo - s) / (e - s))
            b = int(len(text) * min(1.0, (hi - s) / (e - s)))
            parts.append(text[a:b])
        await asyncio.sleep(0.05)
        return "".join(parts)


class _TimedJudge:
    def __init__(self, inner):
        self.inner, self.last, self.seconds = inner, None, 0.0

    async def judge(self, **kw):
        start = time.perf_counter()
        self.last = None
        try:
            self.last = await self.inner.judge(**kw)
            return self.last
        finally:
            self.seconds = time.perf_counter() - start


class _CountingGenerator:
    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    async def generate(self, **kw):
        self.calls += 1
        return await self.inner.generate(**kw)


def _section_at(timeline: list[dict], seconds: float) -> str:
    for sec in timeline:
        if float(sec["start"]) <= seconds < float(sec["end"]):
            return sec["section"]
    return "?"


def _section_of_quote(timeline: list[dict], quote: str) -> str:
    q = _squash(quote)[:20]
    for sec in timeline:
        if q and q in _squash(sec["text"]):
            return sec["section"]
    return "?"


def _overlaps(timeline: list[dict], section: str, start: float, seg: int) -> bool:
    for sec in timeline:
        if sec["section"] == section:
            return float(sec["start"]) < start + seg and float(sec["end"]) > start
    return False


async def _wait(manager: VideoJobManager, job: VideoJob) -> VideoJob:
    last = ""
    while True:
        job = manager.get(SMOKE_USER, job.job_id)
        state = f"{job.stage} {job.progress_done}/{job.progress_total}"
        if state != last:
            print(f"    · {state}")
            last = state
        if job.status != "processing":
            return job
        await asyncio.sleep(0.5)


async def main(args) -> int:
    settings = get_settings()
    setup_logging("WARNING")
    timeline = json.loads(Path(args.fake_asr).read_text(encoding="utf-8")) if args.fake_asr else None
    transcriber = (
        TimelineTranscriber(timeline, settings.video_segment_seconds) if timeline else SiliconFlowTranscriber(settings)
    )
    manager = VideoJobManager(
        settings,
        transcriber=transcriber,
        bilibili=BilibiliClient(settings),
        content_filter=get_content_filter(),
    )
    manager.clear_tmp()
    judge = _TimedJudge(get_web_scope_judge())
    gen = _CountingGenerator(get_web_quiz_generator())
    service = VideoQuizService(manager, judge, gen, settings=settings, content_filter=get_content_filter())
    start_s, end_s = None, None
    if args.range:
        a, b = args.range.split("-")
        start_s, end_s = int(a), int(b)
    print(f"转写：{'讲稿替身' if timeline else settings.asr_model}；每个视频出 {args.n} 次 5 题")
    failures = 0
    try:
        sources = [("upload", v) for v in args.video or []] + [("bilibili", u) for u in args.bilibili or []]
        for kind, item in sources:
            print(f"\n== {item}")
            t0 = time.perf_counter()
            if kind == "upload":
                src = Path(item)
                tmp = manager.upload_path(src.suffix)
                tmp.write_bytes(src.read_bytes())
                job = manager.start_upload(SMOKE_USER, tmp, src.name)
            else:
                url = await manager.resolve_bilibili(item)
                job = manager.start_bilibili(SMOKE_USER, url)
            job = await _wait(manager, job)
            print(
                f"  解析 {time.perf_counter() - t0:.1f}s status={job.status} via={job.via} "
                f"时长 {format_clock(job.duration)} 段 {len(job.segments)} 字 {job.char_count}"
            )
            if job.status != "ready":
                print(f"  失败原因：{job.fail_reason}")
                failures += 1
                continue
            text_all = _squash("".join(s.text for s in job.segments))
            for i in range(1, args.n + 1):
                gen.calls = 0
                t1 = time.perf_counter()
                try:
                    quiz = await service.generate(
                        SMOKE_USER,
                        VideoQuizRequest(job_id=job.job_id, focus=args.focus, start_seconds=start_s, end_seconds=end_s, question_count=5),
                    )
                except BizError as exc:
                    print(f"  第 {i} 次 失败 {exc.code}：{exc.message}")
                    failures += exc.code == 4001
                    continue
                scope = judge.last
                if scope is not None:
                    print(f"  范围判断 {judge.seconds:.1f}s 「{scope.title}」/{scope.topic} 选块 {scope.block_ids}")
                    print(f"  知识点：{'、'.join(scope.knowledge_points)}")
                else:
                    print(f"  范围判断 {judge.seconds:.1f}s 失败（已降级为按时间顺序取材）")
                srcs = [s for q in quiz.questions for s in q.sources]
                found = sum(1 for s in srcs if _squash(s.quote)[:20] in text_all)
                line = f"  第 {i} 次 {time.perf_counter() - t1:.1f}s 尝试 {gen.calls} 次 《{quiz.title}》/{quiz.topic} 摘录在文字稿 {found}/{len(srcs)}"
                if timeline:
                    # 转写按 1 分钟一段，时间点的精度就是这一段：摘录所在那一节和 [时间点, 时间点 + 1 段) 有重叠即算对
                    seg = settings.video_segment_seconds
                    match = sum(1 for s in srcs if _overlaps(timeline, _section_of_quote(timeline, s.quote), s.start_seconds or 0, seg))
                    line += f"，时间点覆盖摘录所在那一节 {match}/{len(srcs)}"
                print(line)
                if args.show:
                    for q in quiz.questions:
                        s = q.sources[0]
                        sec = f" [{_section_at(timeline, s.start_seconds or 0)}]" if timeline else ""
                        print(f"    [{q.type}] {q.stem}  答案 {q.answer}")
                        print(f"        {format_clock(s.start_seconds or 0)}{sec} 摘录：{s.quote[:50]}")
    finally:
        await manager.aclose()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", action="append", help="本地视频文件（可重复）")
    parser.add_argument("--bilibili", action="append", help="B 站链接 / BV 号（可重复）")
    parser.add_argument("--fake-asr", metavar="TIMELINE_JSON", help="转写用讲稿替身（转写服务不可用时验证出题与时间点）")
    parser.add_argument("-n", type=int, default=1, help="每个视频出题次数")
    parser.add_argument("--focus", default="")
    parser.add_argument("--range", help="只学其中一段，秒，如 60-180")
    parser.add_argument("--show", action="store_true")
    a = parser.parse_args()
    if not a.video and not a.bilibili:
        parser.error("至少给一个 --video 或 --bilibili")
    sys.exit(asyncio.run(main(a)))
