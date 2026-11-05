from pydantic import BaseModel, Field

from app.models.quiz import Question


class AnswerRecord(BaseModel):
    question_id: str
    selected_answers: list[str]
    # 前端本地判题结果，仅作参考；后端会按题目答案重新判题
    is_correct: bool = False
    duration_ms: int = Field(ge=0)


class ReportGenerateRequest(BaseModel):
    quiz_id: str
    topic: str = Field(min_length=1, max_length=100)
    questions: list[Question] = Field(min_length=1, max_length=10)
    answer_records: list[AnswerRecord] = Field(max_length=10)


class KnowledgeMastery(BaseModel):
    point: str
    correct: int
    total: int
    accuracy: int


class QuestionResult(BaseModel):
    question_id: str
    selected_answers: list[str]
    is_correct: bool
    duration_ms: int


class ScoreSummary(BaseModel):
    """统计模块的确定性结果，正确率与掌握度以此为准，不交给 AI。"""

    total_count: int
    correct_count: int
    accuracy: int
    total_duration_ms: int
    results: list[QuestionResult]
    knowledge_mastery: list[KnowledgeMastery]
    mastered_points: list[str]
    weak_points: list[str]


class Report(BaseModel):
    accuracy: int
    correct_count: int
    total_count: int
    total_duration_ms: int
    mastered_points: list[str]
    weak_points: list[str]
    knowledge_mastery: list[KnowledgeMastery]
    three_line_summary: list[str]
    advice: list[str]
    share_quote: str
