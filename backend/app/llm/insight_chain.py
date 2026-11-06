"""学习结论链：ChatPromptTemplate | ChatOpenAI.with_structured_output(GeneratedInsight)。"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from app.llm.output_schemas import GeneratedInsight
from app.models.stats import LearningStats
from app.prompts.insight_prompt import DEFAULT_INSIGHT_PROMPT, INSIGHT_PROMPT_VERSIONS, insight_prompt_variables


class InsightGenerator(Protocol):
    async def generate(self, *, stats: LearningStats) -> GeneratedInsight: ...


class LangChainInsightGenerator:
    def __init__(self, llm: BaseChatModel, prompt_version: str = DEFAULT_INSIGHT_PROMPT):
        structured = llm.with_structured_output(GeneratedInsight, method="function_calling")
        self._chain = INSIGHT_PROMPT_VERSIONS[prompt_version] | structured

    async def generate(self, *, stats: LearningStats) -> GeneratedInsight:
        result = await self._chain.ainvoke(insight_prompt_variables(stats))
        if result is None:
            raise ValueError("model returned no tool call")
        return result
