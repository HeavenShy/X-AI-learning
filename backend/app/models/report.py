from pydantic import BaseModel

from app.models.quiz import Question


class AnswerRecord(BaseModel):
    question_id: str
    selected_answers: list[str]
    is_correct: bool
    duration_ms: int


class ReportGenerateRequest(BaseModel):
    quiz_id: str
    topic: str
    questions: list[Question]
    answer_records: list[AnswerRecord]


class Report(BaseModel):
    accuracy: int
    mastered_points: list[str]
    weak_points: list[str]
    three_line_summary: list[str]
    advice: list[str]
    share_quote: str
