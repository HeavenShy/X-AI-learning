"""报告链：ChatPromptTemplate | ChatOpenAI.with_structured_output(GeneratedReport)。"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from app.llm.output_schemas import GeneratedReport
from app.models.quiz import Question
from app.models.report import ScoreSummary
from app.prompts.report_prompt import REPORT_PROMPT_VERSIONS, report_prompt_variables


class ReportGenerator(Protocol):
    async def generate(
        self, *, topic: str, questions: list[Question], summary: ScoreSummary, prompt_version: str
    ) -> GeneratedReport: ...


class LangChainReportGenerator:
    def __init__(self, llm: BaseChatModel):
        structured = llm.with_structured_output(GeneratedReport, method="function_calling")
        self._chains = {version: prompt | structured for version, prompt in REPORT_PROMPT_VERSIONS.items()}

    async def generate(
        self, *, topic: str, questions: list[Question], summary: ScoreSummary, prompt_version: str
    ) -> GeneratedReport:
        variables = report_prompt_variables(topic=topic, questions=questions, summary=summary)
        result = await self._chains[prompt_version].ainvoke(variables)
        if result is None:
            raise ValueError("model returned no tool call")
        return result
