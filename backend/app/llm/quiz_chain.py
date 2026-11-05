"""出题链：ChatPromptTemplate | ChatOpenAI.with_structured_output(GeneratedQuiz)。"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from app.llm.output_schemas import GeneratedQuiz
from app.prompts.quiz_prompt import QUIZ_PROMPT_VERSIONS, quiz_prompt_variables


class QuizGenerator(Protocol):
    async def generate(
        self, *, user_input: str, question_count: int, difficulty: str, prompt_version: str
    ) -> GeneratedQuiz: ...


class LangChainQuizGenerator:
    def __init__(self, llm: BaseChatModel):
        # DeepSeek 不支持 json_schema 方式；function_calling 已实测可用（需关闭思考模式）
        structured = llm.with_structured_output(GeneratedQuiz, method="function_calling")
        self._chains = {version: prompt | structured for version, prompt in QUIZ_PROMPT_VERSIONS.items()}

    async def generate(
        self, *, user_input: str, question_count: int, difficulty: str, prompt_version: str
    ) -> GeneratedQuiz:
        variables = quiz_prompt_variables(user_input=user_input, question_count=question_count, difficulty=difficulty)
        result = await self._chains[prompt_version].ainvoke(variables)
        if result is None:
            raise ValueError("model returned no tool call")
        return result
