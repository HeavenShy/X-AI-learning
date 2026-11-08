"""网页 / 视频出题前的范围判断链：ChatPromptTemplate | ChatOpenAI.with_structured_output(WebPageScope)。"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from app.llm.output_schemas import WebPageScope
from app.prompts.web_scope_prompt import WEB_SCOPE_PROMPTS, SourceKind, web_scope_prompt_variables


class WebScopeJudge(Protocol):
    async def judge(
        self, *, title: str, site: str, blocks: list[str], focus: str, full: bool, kind: SourceKind = "web"
    ) -> WebPageScope: ...


class LangChainWebScopeJudge:
    def __init__(self, llm: BaseChatModel):
        # 与出题相同：DeepSeek 用 function_calling（需关闭思考模式）
        structured = llm.with_structured_output(WebPageScope, method="function_calling")
        self._chains = {kind: prompt | structured for kind, prompt in WEB_SCOPE_PROMPTS.items()}

    async def judge(
        self, *, title: str, site: str, blocks: list[str], focus: str, full: bool, kind: SourceKind = "web"
    ) -> WebPageScope:
        variables = web_scope_prompt_variables(title=title, site=site, blocks=blocks, focus=focus, full=full, kind=kind)
        result = await self._chains[kind].ainvoke(variables)
        if result is None:
            raise ValueError("model returned no tool call")
        return result
