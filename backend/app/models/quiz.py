from typing import Literal

from pydantic import BaseModel, Field

QuestionType = Literal["single", "multiple", "judge"]
Difficulty = Literal["easy", "medium", "hard"]


class Option(BaseModel):
    key: str
    text: str


class Question(BaseModel):
    id: str
    type: QuestionType
    stem: str
    options: list[Option]
    answer: list[str]
    explanation: str
    knowledge_point: str
    difficulty: Difficulty


class QuizGenerateRequest(BaseModel):
    user_input: str = Field(min_length=1, max_length=5000)
    question_count: int = Field(default=5, ge=3, le=5)
    difficulty: Difficulty | Literal["mixed"] = "mixed"


class Quiz(BaseModel):
    quiz_id: str
    title: str
    summary: str
    source_type: Literal["text"] = "text"
    user_input: str
    questions: list[Question]
