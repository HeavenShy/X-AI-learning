from typing import Literal

from pydantic import BaseModel, Field

QuestionType = Literal["single", "multiple", "judge"]
Difficulty = Literal["easy", "medium", "hard"]
DifficultyOption = Literal["mixed", "easy", "medium", "hard"]
QuestionCount = Literal[3, 5, 10]


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
    # 最短长度在服务层校验，以便返回“至少写 4 个字”的友好提示
    user_input: str = Field(max_length=2000)
    question_count: QuestionCount = 5
    difficulty: DifficultyOption = "mixed"


class QuizContent(BaseModel):
    """经过校验与规范化的题库内容（不含 quiz_id 等元信息）。"""

    title: str
    summary: str
    questions: list[Question]


class Quiz(QuizContent):
    quiz_id: str
    source_type: Literal["text"] = "text"
    user_input: str
