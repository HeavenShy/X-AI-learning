"""知识库出题链：ChatPromptTemplate | ChatOpenAI.with_structured_output(GeneratedKbQuiz)。

文本出题的 GeneratedQuiz Schema 不动，这里用单独的 Schema（多了 source_ids、source_quote），
避免影响文本出题发给模型的工具定义。background 是检索规划 Agent 联网查到的背景资料（可为空）。
"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from app.llm.output_schemas import GeneratedKbQuiz
from app.prompts.kb_quiz_prompt import KB_QUIZ_PROMPT_VERSIONS, kb_quiz_prompt_variables


class KbQuizGenerator(Protocol):
    async def generate(
        self,
        *,
        materials: str,
        focus: str,
        question_count: int,
        difficulty: str,
        prompt_version: str,
        background: str = "",
    ) -> GeneratedKbQuiz: ...


class LangChainKbQuizGenerator:
    def __init__(self, llm: BaseChatModel):
        # 与文本出题相同：DeepSeek 用 function_calling（需关闭思考模式）
        structured = llm.with_structured_output(GeneratedKbQuiz, method="function_calling")
        self._chains = {version: prompt | structured for version, prompt in KB_QUIZ_PROMPT_VERSIONS.items()}

    async def generate(
        self,
        *,
        materials: str,
        focus: str,
        question_count: int,
        difficulty: str,
        prompt_version: str,
        background: str = "",
    ) -> GeneratedKbQuiz:
        variables = kb_quiz_prompt_variables(
            materials=materials,
            focus=focus,
            question_count=question_count,
            difficulty=difficulty,
            background=background,
        )
        result = await self._chains[prompt_version].ainvoke(variables)
        if result is None:
            raise ValueError("model returned no tool call")
        return result
