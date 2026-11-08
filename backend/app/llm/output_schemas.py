"""LLM 结构化输出的 Schema。

类名与 docstring 会成为 function calling 的工具名和描述，字段 description 会进入 JSON Schema，
所以这里的中文描述就是给模型看的格式说明。
"""

from typing import Literal

from pydantic import BaseModel, Field

TOPIC_VOCABULARY = "AI 技术、编程、理财、职场、健康、生活常识、科学、历史、语言、心理、艺术"
TOPIC_DESCRIPTION = (
    f"这一话所属的大类主题，用于把用户学过的内容归类。优先从这些词里选一个：{TOPIC_VOCABULARY}；"
    "都不合适时再自拟一个 2–6 个字的大类名（是领域，不是这一话的标题）"
)


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
    topic: str = Field(default="", description=TOPIC_DESCRIPTION)
    summary: str = Field(description="一句话概括这组题覆盖了哪些内容，不超过 50 字")
    questions: list[GeneratedQuestion] = Field(description="题目列表")


class GeneratedReport(BaseModel):
    """提交本次闯关的学习复盘内容。"""

    three_line_summary: list[str] = Field(
        description="三句话记住本话知识，恰好 3 句，每句不超过 30 字，三句连起来像一个小故事"
    )
    advice: list[str] = Field(description="下一步学习建议，2–3 条，每条不超过 30 字，要具体、可执行")
    share_quote: str = Field(description="一句可用于分享海报的学习金句，不超过 20 字")


class GeneratedQuestionWithSources(GeneratedQuestion):
    source_ids: list[int] = Field(
        default_factory=list,
        description="依据 <materials> 资料片段出的题，填所依据的片段编号（片段开头方括号里的数字），1–3 个；没用到资料就留空",
    )
    source_quote: str = Field(
        default="", description="用到资料时，从第一个出处片段原文中照抄的一句话，不改写，不超过 60 字；没用到就留空串"
    )


class GeneratedQuizWithSources(BaseModel):
    """提交一组用于小程序闯关答题的题目；依据资料片段出的题标明出处片段。"""

    title: str = Field(description="这一话的主题名，2–12 个字，例如“RAG 入门”")
    topic: str = Field(default="", description=TOPIC_DESCRIPTION)
    summary: str = Field(description="一句话概括这组题覆盖了哪些内容，不超过 50 字")
    questions: list[GeneratedQuestionWithSources] = Field(description="题目列表")


class GeneratedKbQuestion(GeneratedQuestion):
    source_ids: list[int] = Field(
        description="这道题所依据的资料片段编号（片段开头方括号里的数字），1–3 个，最主要的放第一个"
    )
    source_quote: str = Field(description="从第一个出处片段原文中照抄的一句话，不改写，不超过 60 字")


class GeneratedKbQuiz(BaseModel):
    """提交一组依据用户资料出的闯关题目，每道题都标明出处片段。"""

    title: str = Field(description="这一话的主题名，2–12 个字，概括资料片段讲的内容")
    topic: str = Field(default="", description=TOPIC_DESCRIPTION)
    summary: str = Field(description="一句话概括这组题覆盖了资料里的哪些内容，不超过 50 字")
    questions: list[GeneratedKbQuestion] = Field(description="题目列表")


class GeneratedInsight(BaseModel):
    """提交一句写在学习数据图表下面的学习结论。"""

    insight: str = Field(
        description="一到两句话、不超过 60 字：先点出这段时间最容易错的地方（引用给出的数字），再给一个下次马上能做的具体做法"
    )


class WebPageScope(BaseModel):
    """提交对这篇网页的出题范围判断：主题、要考的知识点、用哪些正文块。"""

    learnable: bool = Field(
        description="网页里有没有可以学习、可以出题的知识内容。登录页、商品列表、导航页、纯广告、几乎没有正文时填 false"
    )
    reason: str = Field(default="", description="learnable 为 false 时，用一句话（不超过 30 字）说明原因；否则留空串")
    title: str = Field(default="", description="这篇网页讲的主题，2–12 个字，例如“RAG 入门”")
    topic: str = Field(default="", description=TOPIC_DESCRIPTION)
    knowledge_points: list[str] = Field(
        default_factory=list,
        description="出题范围：这篇网页里最值得考的 3–8 个知识点，每个 4–16 个字，按重要性排序，互不重复",
    )
    block_ids: list[int] = Field(
        default_factory=list,
        description="承载这些知识点的正文块编号（块开头方括号里的数字），按重要性排序；不要选导航、广告、评论、作者简介、推广和版权声明",
    )
