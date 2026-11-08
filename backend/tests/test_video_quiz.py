"""视频出题：解析任务（真 ffmpeg + 假转写 / 假 B 站）、时间段筛选与拼块、出题服务、Prompt、接口。"""

import asyncio
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_web_quiz_generator, get_web_scope_judge
from app.core.auth import create_token
from app.llm.output_schemas import WebPageScope
from app.main import create_app
from app.models.video import VideoQuizRequest
from app.prompts.web_quiz_prompt import (
    CONSERVATIVE_VIDEO_QUIZ_PROMPT,
    CONSERVATIVE_WEB_QUIZ_PROMPT,
    DEFAULT_VIDEO_QUIZ_PROMPT,
    DEFAULT_WEB_QUIZ_PROMPT,
    build_web_quiz_messages,
)
from app.prompts.web_scope_prompt import build_web_scope_messages
from app.services.bilibili import BiliInfo
from app.services.material_quiz import Block, format_clock
from app.services.video_jobs import MSG_BUSY, MSG_NO_SPEECH, VideoJob, VideoJobManager
from app.services.video_media import TimedText
from app.services.video_quiz_service import VideoQuizService, group_blocks, select_range
from app.utils.content_filter import ContentFilter
from tests.test_video_media import make_video
from tests.test_web_quiz import FakeGenerator, FakeJudge
from tests.llm_mock import test_settings

SPEECH = "复利就是利滚利，每一期的利息都会加入本金，下一期一起计算利息。"


class FakeTranscriber:
    def __init__(self, text: str = SPEECH * 3, delay: float = 0.0):
        self.text = text
        self.delay = delay
        self.calls = 0

    async def transcribe(self, path: Path) -> str:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return f"{path.stem}：{self.text}"


class FakeBili:
    def __init__(self, *, duration: float = 120, subtitles=None, audio: Path | None = None, title: str = "两分钟讲复利"):
        self.duration = duration
        self.subs = subtitles or []
        self.audio = audio
        self.title = title

    async def resolve(self, raw: str) -> str:
        return "https://www.bilibili.com/video/BV1ns411w7tt"

    async def info(self, url: str) -> BiliInfo:
        return BiliInfo(video_id="BV1ns411w7tt", title=self.title, duration=self.duration, url=url)

    async def subtitles(self, info) -> list[TimedText]:
        return self.subs

    async def download_audio(self, url: str, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "audio.mp4"
        target.write_bytes(self.audio.read_bytes())
        return target


def manager(tmp_path, *, transcriber=None, bilibili=None, **kw) -> VideoJobManager:
    s = test_settings(video_tmp_dir=str(tmp_path / "vt"), video_segment_seconds=2, **kw)
    m = VideoJobManager(
        s, transcriber=transcriber or FakeTranscriber(), bilibili=bilibili, content_filter=ContentFilter(["制毒"])
    )
    m.clear_tmp()
    return m


async def wait_done(m: VideoJobManager, user_id: int, job_id: str) -> VideoJob:
    for _ in range(200):
        job = m.get(user_id, job_id)
        if job.status != "processing":
            return job
        await asyncio.sleep(0.05)
    raise AssertionError("job did not finish")


def upload(m: VideoJobManager, tmp_path, *, seconds=5, audio=True, name="复利入门.mp4"):
    src = make_video(m.upload_path(".mp4"), seconds=seconds, audio=audio)
    return m.start_upload(1, src, name)


# ---------- 解析任务 ----------


async def test_upload_job_transcribes_segments_with_times(tmp_path):
    t = FakeTranscriber()
    m = manager(tmp_path, transcriber=t)
    job = upload(m, tmp_path)
    assert job.status == "processing" and job.title == "复利入门"
    job = await wait_done(m, 1, job.job_id)
    assert job.status == "ready", job.fail_reason
    assert job.via == "asr" and job.progress_total == 3 and job.progress_done == 3
    assert [(s.start, round(s.end)) for s in job.segments] == [(0.0, 2), (2.0, 4), (4.0, 5)]
    assert job.segments[0].text.startswith("part_0000")
    # 临时文件都删了
    assert list((tmp_path / "vt").iterdir()) == []


async def test_silent_video_fails_with_reason(tmp_path):
    m = manager(tmp_path)
    job = await wait_done(m, 1, upload(m, tmp_path, audio=False).job_id)
    assert job.status == "failed" and "没有声音" in job.fail_reason


async def test_too_long_video_fails(tmp_path):
    m = manager(tmp_path, video_max_seconds=3)
    job = await wait_done(m, 1, upload(m, tmp_path, seconds=5).job_id)
    assert job.status == "failed" and "超过 0 分钟" not in job.fail_reason and "剪出" in job.fail_reason


async def test_no_speech_fails(tmp_path):
    m = manager(tmp_path, transcriber=FakeTranscriber(text=""))

    class Empty(FakeTranscriber):
        async def transcribe(self, path):
            return ""

    m = manager(tmp_path, transcriber=Empty())
    job = await wait_done(m, 1, upload(m, tmp_path).job_id)
    assert job.status == "failed" and job.fail_reason == MSG_NO_SPEECH


async def test_sensitive_segments_are_dropped(tmp_path):
    class Mixed(FakeTranscriber):
        async def transcribe(self, path):
            return "教你制毒" if path.stem.endswith("1") else SPEECH * 3

    m = manager(tmp_path, transcriber=Mixed())
    job = await wait_done(m, 1, upload(m, tmp_path).job_id)
    assert job.status == "ready"
    assert all("制毒" not in s.text for s in job.segments) and len(job.segments) == 2


async def test_one_processing_job_per_user(tmp_path):
    m = manager(tmp_path, transcriber=FakeTranscriber(delay=0.3))
    job = upload(m, tmp_path)
    with pytest.raises(Exception) as e:
        m.check_idle(1)
    assert e.value.code == 4022 and e.value.message == MSG_BUSY
    m.check_idle(2)  # 别人不受影响
    await wait_done(m, 1, job.job_id)
    m.check_idle(1)


async def test_job_is_private_and_expires(tmp_path):
    now = [100.0]
    m = manager(tmp_path)
    m._clock = lambda: now[0]
    job = await wait_done(m, 1, upload(m, tmp_path).job_id)
    assert m.get(2, job.job_id) is None
    now[0] += 7201
    assert m.get(1, job.job_id) is None


async def test_bilibili_subtitles_skip_transcription(tmp_path):
    t = FakeTranscriber()
    subs = [TimedText(0, 30, SPEECH * 2), TimedText(60, 90, SPEECH * 2)]
    m = manager(tmp_path, transcriber=t, bilibili=FakeBili(subtitles=subs))
    job = m.start_bilibili(1, "https://www.bilibili.com/video/BV1ns411w7tt")
    job = await wait_done(m, 1, job.job_id)
    assert job.status == "ready" and job.via == "subtitle" and job.title == "两分钟讲复利"
    assert job.url == "https://www.bilibili.com/video/BV1ns411w7tt"
    assert t.calls == 0


async def test_bilibili_without_subtitles_downloads_audio(tmp_path):
    audio = make_video(tmp_path / "src.mp4", seconds=3)
    m = manager(tmp_path, bilibili=FakeBili(audio=audio))
    job = await wait_done(m, 1, m.start_bilibili(1, "https://www.bilibili.com/video/BV1ns411w7tt").job_id)
    assert job.status == "ready" and job.via == "asr" and len(job.segments) == 2


async def test_bilibili_too_long_fails_before_download(tmp_path):
    m = manager(tmp_path, bilibili=FakeBili(duration=3600))
    job = await wait_done(m, 1, m.start_bilibili(1, "https://www.bilibili.com/video/BV1ns411w7tt").job_id)
    assert job.status == "failed" and "30 分钟" in job.fail_reason


# ---------- 时间段与拼块 ----------


SEGMENTS = [TimedText(i * 60.0, (i + 1) * 60.0, f"第{i}分钟" + "讲" * 200) for i in range(6)]


def test_select_range():
    assert len(select_range(SEGMENTS, None, None)) == 6
    assert [s.start for s in select_range(SEGMENTS, 130, 200)] == [120.0, 180.0]
    assert select_range(SEGMENTS, 400, 500) == []


def test_group_blocks_keeps_time():
    blocks = group_blocks(SEGMENTS, chunk_chars=500)
    assert [(b.start, b.end) for b in blocks] == [(0, 120), (120, 240), (240, 360)]
    assert blocks[0].label == "00:00–02:00"
    assert [p[0] for p in blocks[0].parts] == [0.0, 60.0]


def test_block_time_of_quote():
    block = group_blocks(
        [TimedText(0, 60, "复利就是利滚利，利息并入本金。"), TimedText(60, 120, "单利只按最初的本金计算利息。")], chunk_chars=500
    )[0]
    assert block.time_of("单利只按最初的本金计算利息") == 60
    assert block.time_of("复利就是利滚利") == 0
    # 摘录跨两段：取开头所在的那一段
    assert block.time_of("并入本金。单利只按最初") == 0
    assert block.time_of("完全对不上的话") == 0
    assert Block("网页正文").time_of("网页") is None
    assert format_clock(3725) == "1:02:05"
    assert Block("x").label is None


# ---------- 出题 ----------


def ready_manager(segments=SEGMENTS, url=None) -> VideoJobManager:
    m = VideoJobManager(test_settings(), transcriber=FakeTranscriber(), bilibili=None, content_filter=ContentFilter(["制毒"]))
    job = VideoJob(job_id="vj_1", user_id=1, source="bilibili" if url else "upload", title="复利入门", url=url,
                   status="ready", stage="done", duration=360, segments=list(segments), via="asr")
    job.updated_at = m._clock()
    m._jobs[job.job_id] = job
    return m


def video_service(m, judge=None, gen=None):
    judge = judge or FakeJudge(WebPageScope(learnable=True, topic="理财", knowledge_points=["复利"], block_ids=[2, 1]))
    gen = gen or FakeGenerator()
    return VideoQuizService(m, judge, gen, settings=test_settings(), content_filter=ContentFilter(["制毒"])), judge, gen


async def test_video_quiz_sources_have_time_and_url():
    svc, judge, gen = video_service(ready_manager(url="https://www.bilibili.com/video/BV1ns411w7tt"))
    quiz = await svc.generate(1, VideoQuizRequest(job_id="vj_1", question_count=3))
    assert quiz.source_type == "video" and quiz.user_input == "复利入门"
    assert judge.calls[0]["kind"] == "video" and judge.calls[0]["blocks"][0].startswith("00:00–02:00 ")
    call = gen.calls[0]
    assert call["prompt_version"] == DEFAULT_VIDEO_QUIZ_PROMPT
    assert re.findall(r"^\[\d+\] 《复利入门》(\S+)$", call["materials"], re.M) == ["00:00–02:00", "02:00–04:00"]
    starts = {s.start_seconds for q in quiz.questions for s in q.sources}
    assert starts <= {0, 120} and starts
    assert all(s.url == "https://www.bilibili.com/video/BV1ns411w7tt" and s.page is None for q in quiz.questions for s in q.sources)


async def test_video_quiz_range_and_errors():
    svc, judge, gen = video_service(ready_manager())
    quiz = await svc.generate(1, VideoQuizRequest(job_id="vj_1", start_seconds=200, end_seconds=300, question_count=3, focus="复利公式"))
    assert all(s.start_seconds >= 180 for q in quiz.questions for s in q.sources)
    assert all(s.url is None for q in quiz.questions for s in q.sources)
    assert quiz.user_input == "复利公式"
    with pytest.raises(Exception) as e:
        await svc.generate(1, VideoQuizRequest(job_id="vj_1", start_seconds=900, question_count=3))
    assert e.value.code == 4054
    with pytest.raises(Exception) as e:
        await svc.generate(2, VideoQuizRequest(job_id="vj_1", question_count=3))
    assert e.value.code == 4040
    m = ready_manager()
    m._jobs["vj_1"].status = "processing"
    with pytest.raises(Exception) as e:
        await video_service(m)[0].generate(1, VideoQuizRequest(job_id="vj_1", question_count=3))
    assert e.value.code == 4053


async def test_video_not_learnable_message():
    svc, _, _ = video_service(ready_manager(), judge=FakeJudge(WebPageScope(learnable=False, reason="只有背景音乐")))
    with pytest.raises(Exception) as e:
        await svc.generate(1, VideoQuizRequest(job_id="vj_1", question_count=3))
    assert e.value.code == 4032 and "这段视频" in e.value.message and "只有背景音乐" in e.value.message


def test_quiz_request_range_validation():
    with pytest.raises(ValueError):
        VideoQuizRequest(job_id="vj_1", start_seconds=60, end_seconds=30)


# ---------- Prompt ----------


def test_web_prompts_unchanged_by_kind():
    golden = json.loads((Path(__file__).parent / "golden" / "web_prompts_before_kind.json").read_text(encoding="utf-8"))

    def dump(msgs):
        return [{"type": m.type, "content": m.content} for m in msgs]

    for version in (DEFAULT_WEB_QUIZ_PROMPT, CONSERVATIVE_WEB_QUIZ_PROMPT):
        for name, kw in {"plain": dict(knowledge_points=[], focus=""), "rich": dict(knowledge_points=["RAG 的两步", "向量检索"], focus="和微调怎么选")}.items():
            got = dump(build_web_quiz_messages(version, materials="[1] 《一文看懂 RAG》\n正文一\n\n[2] 《一文看懂 RAG》\n正文二",
                                               question_count=5, difficulty="mixed", single_answer_keys=["B", "D", "A"], **kw))
            assert got == golden[f"quiz/{version}/{name}"]
    assert dump(build_web_scope_messages(title="一文看懂 RAG", site="blog.example.com", blocks=["正文一", "正文二"], focus="", full=True)) == golden["scope/full"]
    assert dump(build_web_scope_messages(title="一文看懂 RAG", site="blog.example.com", blocks=["甲" * 300, "乙"], focus="和微调怎么选", full=False)) == golden["scope/preview_focus"]


def test_video_prompts_wording():
    msgs = build_web_quiz_messages(CONSERVATIVE_VIDEO_QUIZ_PROMPT, materials="[1] 《复利入门》00:00–01:00\n正文",
                                   knowledge_points=["复利"], focus="", question_count=3, difficulty="mixed")
    system, human = msgs[0].content, msgs[-1].content
    assert "同音错字" in system and "不要出现时间点" in system and "只考视频里讲得最明确的内容" in system
    assert "这段视频要考的知识点" in human and "视频文字稿片段如下" in human
    assert "网页" not in system + human
    scope = build_web_scope_messages(kind="video", title="复利入门", site="上传的视频", blocks=["00:00–01:00 正文"], focus="公式", full=True)
    assert "视频名：复利入门" in scope[-1].content and "求关注点赞" in scope[0].content and "网页" not in scope[0].content


# ---------- 接口 ----------


def api(m: VideoJobManager | None, **settings_kw):
    s = test_settings(**settings_kw)
    app = create_app(s)
    app.state.video_jobs = m
    app.dependency_overrides[get_web_scope_judge] = lambda: FakeJudge(WebPageScope(learnable=True, block_ids=[1]))
    app.dependency_overrides[get_web_quiz_generator] = lambda: FakeGenerator()
    token = create_token(1, "openid-1", s)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_api_requires_login_and_availability():
    client, auth = api(ready_manager())
    assert client.get("/api/v1/video/jobs/vj_1").status_code == 401
    client, auth = api(None)
    resp = client.get("/api/v1/video/jobs/vj_1", headers=auth)
    assert resp.status_code == 503 and resp.json()["code"] == 5000


def test_api_job_status_and_quiz():
    client, auth = api(ready_manager())
    body = client.get("/api/v1/video/jobs/vj_1", headers=auth).json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ready" and body["data"]["duration_seconds"] == 360
    assert body["data"]["char_count"] > 0 and body["data"]["via"] == "asr"
    assert client.get("/api/v1/video/jobs/vj_nope", headers=auth).json()["code"] == 4040
    body = client.post("/api/v1/video/quiz", json={"job_id": "vj_1", "question_count": 3}, headers=auth).json()
    assert body["code"] == 0 and body["data"]["source_type"] == "video"
    assert body["data"]["questions"][0]["sources"][0]["start_seconds"] is not None
    bad = client.post("/api/v1/video/quiz", json={"job_id": "vj_1", "start_seconds": 60, "end_seconds": 10}, headers=auth).json()
    assert bad["code"] == 4000


def test_api_upload_rejects_type_and_size(tmp_path):
    m = manager(tmp_path)
    client, auth = api(m, video_max_upload_bytes=1000)
    r = client.post("/api/v1/video/uploads", files={"file": ("a.pdf", b"%PDF-", "application/pdf")}, headers=auth).json()
    assert r["code"] == 4050
    r = client.post("/api/v1/video/uploads", files={"file": ("a.mp4", b"x" * 2000, "video/mp4")}, headers=auth).json()
    assert r["code"] == 4051
    assert [p for p in (tmp_path / "vt").iterdir()] == []


def test_api_upload_starts_job(tmp_path):
    src = make_video(tmp_path / "src.mp4", seconds=3)
    m = manager(tmp_path)
    client, auth = api(m)
    r = client.post("/api/v1/video/uploads", files={"file": ("复利入门.mp4", src.read_bytes(), "video/mp4")}, headers=auth).json()
    assert r["code"] == 0 and r["data"]["status"] == "processing" and r["data"]["title"] == "复利入门"


def test_api_link_rejects_other_sites(tmp_path):
    class Rejecting(FakeBili):
        async def resolve(self, raw):
            from app.services.bilibili import BilibiliError
            raise BilibiliError("只支持 B 站视频链接", kind="invalid")

    client, auth = api(manager(tmp_path, bilibili=Rejecting()))
    r = client.post("/api/v1/video/links", json={"url": "https://v.qq.com/x"}, headers=auth).json()
    assert r["code"] == 4052
    client, auth = api(manager(tmp_path))  # 没有 B 站客户端
    assert client.post("/api/v1/video/links", json={"url": "BV1ns411w7tt"}, headers=auth).json()["code"] == 4052
