from typing import Literal

from pydantic import BaseModel, Field

from app.models.quiz import DifficultyOption, QuestionCount

DocumentStatus = Literal["processing", "ready", "failed"]
FileType = Literal["pdf", "docx", "txt", "md"]


class KbNameRequest(BaseModel):
    # 1–20 字与敏感词在服务层校验，以便返回友好提示
    name: str = Field(max_length=100)


class KnowledgeBase(BaseModel):
    kb_id: str
    name: str
    document_count: int
    # 可出题（ready）的资料数
    ready_count: int
    # ISO 8601 UTC
    created_at: str
    updated_at: str


class KbList(BaseModel):
    items: list[KnowledgeBase]
    total: int
    # 该用户所有知识库合计的资料数与上限
    document_total: int
    document_limit: int


class KbDocument(BaseModel):
    document_id: str
    filename: str
    file_type: FileType
    size_bytes: int
    status: DocumentStatus
    # 仅失败时有
    fail_reason: str | None = None
    # 仅 PDF 有
    page_count: int | None = None
    char_count: int
    # 上传时间，ISO 8601 UTC
    created_at: str


class KbDetail(BaseModel):
    knowledge_base: KnowledgeBase
    documents: list[KbDocument]


class KbQuizRequest(BaseModel):
    # 不传或为空：该库全部资料
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    # 想重点学什么（选填）
    focus: str = Field(default="", max_length=200)
    question_count: QuestionCount = 5
    difficulty: DifficultyOption = "mixed"
