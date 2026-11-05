from pydantic import BaseModel, Field

from app.models.quiz import DifficultyOption, Quiz
from app.models.report import AnswerRecord, Report


class LoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128, description="wx.login() 拿到的 code")


class UserBrief(BaseModel):
    id: int
    nickname: str
    avatar_url: str
    total_xp: int
    total_coins: int


class LoginResponse(BaseModel):
    token: str
    user: UserBrief


class Profile(UserBrief):
    # 已学话数（完结的闯关次数）
    quiz_count: int
    correct_count: int
    question_count: int
    # 总正确率：累计答对题数 / 累计题数，整数百分比
    average_accuracy: int
    # 本周学习分钟（北京时间周一 0 点起）
    week_minutes: int


class ProfileUpdate(BaseModel):
    """只传要改的字段。昵称长度与敏感词在服务层校验，以便返回友好提示。"""

    nickname: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=500)


class HistoryItem(BaseModel):
    quiz_id: str
    title: str
    question_count: int
    correct_count: int
    accuracy: int
    total_duration_ms: int
    has_report: bool
    # 完结时间，ISO 8601 UTC（如 2026-11-05T02:03:04Z）
    created_at: str


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    total: int
    page: int
    page_size: int


class Reward(BaseModel):
    xp: int
    coins: int


class QuizDetail(BaseModel):
    quiz: Quiz
    difficulty: DifficultyOption
    answer_records: list[AnswerRecord]
    accuracy: int
    correct_count: int
    total_count: int
    total_duration_ms: int
    reward: Reward
    # AI 复盘生成失败时为 null，前端可用题目和答题记录重新生成
    report: Report | None
    # 这是该用户的第几话（海报“我的第 N 话”）
    episode: int
    created_at: str
