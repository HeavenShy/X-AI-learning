from typing import Literal

from pydantic import BaseModel

from app.models.quiz import QuestionType

StatsRange = Literal["week", "month", "all"]


class StatsBar(BaseModel):
    # 柱子下的标签：本周“一 … 日 / 今天”，本月“第 N 周”，全部“N 月”
    label: str
    minutes: int
    # 是否是当前这一格（今天 / 本周 / 本月）
    is_current: bool


class TypeAccuracy(BaseModel):
    type: QuestionType
    correct: int
    total: int
    # 整数百分比；没有这类题时为 0
    accuracy: int


class LearningStats(BaseModel):
    range: StatsRange
    # 如“11 月 3 日 – 9 日”“11 月”“全部”
    period_label: str
    total_minutes: int
    # 上一周期（上周 / 上月）的分钟数；range=all 时为 null
    prev_minutes: int | None
    bars: list[StatsBar]
    # 时间段内完结的话数与题数
    quiz_count: int
    question_count: int
    type_accuracy: list[TypeAccuracy]
    # 多选题答错且选的是正确答案的一部分（漏选）的次数
    multiple_missed: int
    # 正确率最低的最多 3 个知识点（只取有答错的）
    weak_points: list[str]


class StatsInsight(BaseModel):
    # AI 写的一句学习结论；没有数据或生成失败时为 null
    insight: str | None


class TreeQuiz(BaseModel):
    quiz_id: str
    title: str
    # 出题时的原始输入（“再闯一轮”在没有答错知识点时用它）
    user_input: str
    correct: int
    total: int
    accuracy: int
    # 这一话答错的知识点，按题序去重
    weak_points: list[str]
    # 完结时间，ISO 8601 UTC
    finished_at: str


class TreeTopic(BaseModel):
    topic: str
    quiz_count: int
    correct: int
    total: int
    accuracy: int
    quizzes: list[TreeQuiz]


class KnowledgeTree(BaseModel):
    topic_count: int
    topics: list[TreeTopic]
