"""出题链：ChatPromptTemplate | ChatOpenAI.with_structured_output(...)。

没有知识库资料时用 GeneratedQuiz（发给模型的工具定义与之前一致）；检索规划 Agent 查到资料片段时
改用 GeneratedQuizWithSources（题目多了可选的 source_ids、source_quote）。
"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from app.llm.output_schemas import GeneratedQuiz, GeneratedQuizWithSources
from app.prompts.quiz_prompt import QUIZ_PROMPT_VERSIONS, quiz_prompt_variables


class QuizGenerator(Protocol):
    async def generate(
        self,
        *,
        user_input: str,
        question_count: int,
        difficulty: str,
        prompt_version: str,
        reference: str = "",
        materials: str = "",
    ) -> GeneratedQuiz | GeneratedQuizWithSources: ...


class LangChainQuizGenerator:
    def __init__(self, llm: BaseChatModel):
        # DeepSeek 不支持 json_schema 方式；function_calling 已实测可用（需关闭思考模式）
        plain = llm.with_structured_output(GeneratedQuiz, method="function_calling")
        with_sources = llm.with_structured_output(GeneratedQuizWithSources, method="function_calling")
        self._chains = {version: prompt | plain for version, prompt in QUIZ_PROMPT_VERSIONS.items()}
        self._source_chains = {version: prompt | with_sources for version, prompt in QUIZ_PROMPT_VERSIONS.items()}

    async def generate(
        self,
        *,
        user_input: str,
        question_count: int,
        difficulty: str,
        prompt_version: str,
        reference: str = "",
        materials: str = "",
    ) -> GeneratedQuiz | GeneratedQuizWithSources:
        variables = quiz_prompt_variables(
            user_input=user_input,
            question_count=question_count,
            difficulty=difficulty,
            reference=reference,
            materials=materials,
        )
        chains = self._source_chains if materials else self._chains
        result = await chains[prompt_version].ainvoke(variables)
        if result is None:
            raise ValueError("model returned no tool call")
        return result
