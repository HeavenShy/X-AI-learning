from app.core.exceptions import BizError
from app.models.quiz import Quiz, QuizGenerateRequest


async def generate_quiz(req: QuizGenerateRequest) -> Quiz:
    # TODO: 接入 app/llm/quiz_chain（ChatPromptTemplate + ChatOpenAI.with_structured_output）
    raise BizError(code=5001, message="题库生成功能尚未实现")
