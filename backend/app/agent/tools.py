"""检索规划 Agent 可调用的两个只读工具的参数模型。

model_config 的 title 就是发给模型的工具名，docstring 是工具描述，字段 description 进入 JSON Schema。
长度在执行时截断（见 RetrievalPlanner），这里不用 max_length 拒绝，避免模型多写几个字整次调用作废。
"""

from pydantic import BaseModel, ConfigDict, Field

KB_TOOL = "search_knowledge_base"
WEB_TOOL = "web_search"


class SearchKnowledgeBase(BaseModel):
    """在用户自己的知识库资料里做语义检索，返回最相关的资料片段预览。"""

    model_config = ConfigDict(title=KB_TOOL)

    query: str = Field(description="检索查询词：一个具体的主题或问题，不超过 200 字；多个方面请分开多次检索")


class WebSearch(BaseModel):
    """联网搜索公开网页，返回标题和摘要预览。"""

    model_config = ConfigDict(title=WEB_TOOL)

    query: str = Field(
        description="搜索查询词：只写通用主题词，不超过 100 字；不要包含资料原文、人名、公司内部信息"
    )


TOOL_MODELS: dict[str, type[BaseModel]] = {KB_TOOL: SearchKnowledgeBase, WEB_TOOL: WebSearch}
