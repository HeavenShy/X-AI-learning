"""LLM 结构化输出的 Schema。

类名与 docstring 会成为 function calling 的工具名和描述，字段 description 会进入 JSON Schema，
所以这里的中文描述就是给模型看的格式说明。
"""

from typing import Literal

from pydantic import BaseModel, Field


class GeneratedOption(BaseModel):
    key: str = Field(description="选项字母：选择题依次为 A、B、C、D；判断题固定 A=对、B=错")
    text: str = Field(description="选项内容，简短清楚")


class GeneratedQuestion(BaseModel):
    type: Literal["single", "multiple", "judge"] = Field(description="题型：single 单选、multiple 多选、judge 判断")
    stem: str = Field(description="题干，一句话问清楚，不要带题号")
    options: list[GeneratedOption] = Field(description="选项：单选、多选各 4 个；判断题 2 个")
    answer: list[str] = Field(description="正确选项的字母列表。单选、判断 1 个；多选 2–4 个")
    explanation: str = Field(description="讲解：先说为什么对，再点出易错选项错在哪；2–4 句，可用换行分段")
    knowledge_point: str = Field(description="这道题考的知识点，4–12 个字的短语")
    difficulty: Literal["easy", "medium", "hard"] = Field(description="难度")


class GeneratedQuiz(BaseModel):
    """提交一组用于小程序闯关答题的题目。"""

    title: str = Field(description="这一话的主题名，2–12 个字，例如“RAG 入门”")
    summary: str = Field(description="一句话概括这组题覆盖了哪些内容，不超过 50 字")
    questions: list[GeneratedQuestion] = Field(description="题目列表")


class GeneratedReport(BaseModel):
    """提交本次闯关的学习复盘内容。"""

    three_line_summary: list[str] = Field(
        description="三句话记住本话知识，恰好 3 句，每句不超过 30 字，三句连起来像一个小故事"
    )
    advice: list[str] = Field(description="下一步学习建议，2–3 条，每条不超过 30 字，要具体、可执行")
    share_quote: str = Field(description="一句可用于分享海报的学习金句，不超过 20 字")
