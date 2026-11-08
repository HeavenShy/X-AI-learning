"""网页 / 视频出题链：ChatPromptTemplate | ChatOpenAI.with_structured_output(GeneratedKbQuiz)。

输出结构与知识库出题相同（每题 source_ids、source_quote）。为所有版本（web_* / video_*）建链，
来源由版本名决定。
"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from app.llm.output_schemas import GeneratedKbQuiz
from app.prompts.web_quiz_prompt import WEB_QUIZ_PROMPT_VERSIONS, _kind_of, web_quiz_prompt_variables


class WebQuizGenerator(Protocol):
    async def generate(
        self,
        *,
        materials: str,
        knowledge_points: list[str],
        focus: str,
        question_count: int,
        difficulty: str,
        prompt_version: str,
    ) -> GeneratedKbQuiz: ...


class LangChainWebQuizGenerator:
    def __init__(self, llm: BaseChatModel):
        structured = llm.with_structured_output(GeneratedKbQuiz, method="function_calling")
        self._chains = {version: prompt | structured for version, prompt in WEB_QUIZ_PROMPT_VERSIONS.items()}

    async def generate(
        self,
        *,
        materials: str,
        knowledge_points: list[str],
        focus: str,
        question_count: int,
        difficulty: str,
        prompt_version: str,
    ) -> GeneratedKbQuiz:
        variables = web_quiz_prompt_variables(
            materials=materials,
            knowledge_points=knowledge_points,
            focus=focus,
            question_count=question_count,
            difficulty=difficulty,
            kind=_kind_of(prompt_version),
        )
        result = await self._chains[prompt_version].ainvoke(variables)
        if result is None:
            raise ValueError("model returned no tool call")
        return result
