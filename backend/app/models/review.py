from pydantic import BaseModel, Field

from app.models.quiz import Question


class MistakeItem(BaseModel):
    quiz_id: str
    # 所属话的标题（列表按话分组时的组标题）
    quiz_title: str
    # 完整题目（含答案与讲解）：前端重做时本地判题播动画，掌握状态以服务端为准
    question: Question
    # 上次的错误答案：重做答错过取最近一次，否则取闯关时的选项（未作答为空数组）
    last_selected_answers: list[str]
    # 累计答错次数 = 闯关那次 1 + 重做又答错的次数
    wrong_count: int
    # 首次答错时间（该话完结时间），ISO 8601 UTC
    first_wrong_at: str


class MistakeList(BaseModel):
    items: list[MistakeItem]
    total: int


class ReviewAnswerRequest(BaseModel):
    quiz_id: str = Field(min_length=1, max_length=64)
    question_id: str = Field(min_length=1, max_length=64)
    selected_answers: list[str] = Field(max_length=10)


class ReviewAnswerResult(BaseModel):
    is_correct: bool
    correct_answers: list[str]
    # 提交后该题是否已掌握（已移出错题本）
    mastered: bool
