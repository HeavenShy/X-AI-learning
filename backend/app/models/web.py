from typing import Literal

from pydantic import BaseModel, Field

from app.models.quiz import DifficultyOption, QuestionCount

URL_MAX_CHARS = 2000


class WebPreviewRequest(BaseModel):
    url: str = Field(max_length=URL_MAX_CHARS)


class WebPreview(BaseModel):
    """网页预览：让用户确认是这篇再出题。"""

    # 跳转后的最终地址
    url: str
    site: str
    title: str
    # 正文可见字数
    char_count: int
    # 按每分钟约 450 字估算，至少 1 分钟
    read_minutes: int
    via: Literal["local", "tavily"]


class WebQuizRequest(BaseModel):
    url: str = Field(max_length=URL_MAX_CHARS)
    focus: str = Field(default="", max_length=200)
    question_count: QuestionCount = 5
    difficulty: DifficultyOption = "mixed"
