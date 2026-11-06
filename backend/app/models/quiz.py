from typing import Literal

from pydantic import BaseModel, Field

QuestionType = Literal["single", "multiple", "judge"]
Difficulty = Literal["easy", "medium", "hard"]
DifficultyOption = Literal["mixed", "easy", "medium", "hard"]
QuestionCount = Literal[3, 5, 10]
SourceType = Literal["text", "knowledge_base"]


class Option(BaseModel):
    key: str
    text: str


class QuestionSource(BaseModel):
    """知识库出题的出处快照：资料删除后仍随题目保留。"""

    document_id: str
    document_name: str
    # PDF 有页码，Word / TXT / Markdown 为 null
    page: int | None = None
    # 不超过 120 字的原文摘录
    quote: str


class Question(BaseModel):
    id: str
    type: QuestionType
    stem: str
    options: list[Option]
    answer: list[str]
    explanation: str
    knowledge_point: str
    difficulty: Difficulty
    # 知识库出的题至少 1 项；文本出题为空列表（旧的 questions_json 没有该字段，还原时也为空）
    sources: list[QuestionSource] = Field(default_factory=list)


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
    source_type: SourceType = "text"
    user_input: str
