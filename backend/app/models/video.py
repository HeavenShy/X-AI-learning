from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.quiz import DifficultyOption, QuestionCount


class VideoLinkRequest(BaseModel):
    url: str = Field(max_length=2000)


class VideoJobOut(BaseModel):
    """视频解析任务的状态（前端每 2 秒轮询一次）。"""

    job_id: str
    source: Literal["upload", "bilibili"]
    # 上传为文件名（去掉扩展名），B 站为视频标题（取到信息前为“B 站视频”）
    title: str
    # B 站视频的链接；上传为 null
    url: str | None
    status: Literal["processing", "ready", "failed"]
    # download：下载 / 读取视频；extract：提取音频；transcribe：转文字；done：完成
    stage: Literal["download", "extract", "transcribe", "done"]
    progress_done: int
    progress_total: int
    duration_seconds: int
    # 文字稿来源：subtitle（B 站字幕）/ asr（语音识别）；还没开始转写时为 null
    via: Literal["asr", "subtitle"] | None
    # 文字稿可见字数（ready 后才有）
    char_count: int
    fail_reason: str | None


class VideoQuizRequest(BaseModel):
    job_id: str = Field(max_length=64)
    focus: str = Field(default="", max_length=200)
    # 只学其中一段（秒，选填）；都不填为整段视频
    start_seconds: int | None = Field(default=None, ge=0)
    end_seconds: int | None = Field(default=None, ge=1)
    question_count: QuestionCount = 5
    difficulty: DifficultyOption = "mixed"

    @model_validator(mode="after")
    def _range(self):
        if self.start_seconds is not None and self.end_seconds is not None and self.end_seconds <= self.start_seconds:
            raise ValueError("结束时间要晚于开始时间")
        return self
