"""出题重试循环（文本出题与知识库出题共用）。

最多 attempts 次：第 1 次用常规 Prompt，之后换保守 Prompt。每次调用 attempt(prompt_version) 得到
已校验规范化的题库，再过一遍输出敏感词。结构化失败、校验不通过、超时、网络错误都换 Prompt 重试；
Key 错误、权限、请求参数错误这类换 Prompt 也没用的异常直接失败。全部失败返回 4001。
"""

import logging
import time
from collections.abc import Awaitable, Callable

import openai

from app.core.exceptions import BizError, ErrorCode
from app.models.quiz import QuizContent
from app.services.quiz_validator import QuizValidationError
from app.utils.content_filter import ContentFilter

logger = logging.getLogger(__name__)

MSG_GENERATE_FAILED = "题库生成失败，请稍后重试"

NON_RETRYABLE = (openai.AuthenticationError, openai.PermissionDeniedError, openai.BadRequestError)


def quiz_texts(content: QuizContent) -> list[str]:
    texts = [content.title, content.summary]
    for q in content.questions:
        texts += [q.stem, q.explanation, q.knowledge_point, *(o.text for o in q.options)]
    return texts


async def generate_with_retries(
    attempt: Callable[[str], Awaitable[QuizContent]],
    *,
    attempts: int,
    default_prompt: str,
    conservative_prompt: str,
    content_filter: ContentFilter,
) -> QuizContent:
    for n in range(1, attempts + 1):
        version = default_prompt if n == 1 else conservative_prompt
        start = time.perf_counter()
        try:
            content = await attempt(version)
            hit = next((w for t in quiz_texts(content) if (w := content_filter.find(t))), None)
            if hit:
                raise QuizValidationError(f"generated content hit sensitive word {hit!r}")
        except NON_RETRYABLE as exc:
            logger.error("quiz generation aborted (non-retryable): %r", exc)
            raise BizError(ErrorCode.QUIZ_GENERATE_FAILED, MSG_GENERATE_FAILED) from exc
        except Exception as exc:  # noqa: BLE001 —— 结构化失败、超时、网络错误都换 Prompt 重试
            logger.warning(
                "quiz attempt %d/%d (%s) failed after %.1fs: %r",
                n, attempts, version, time.perf_counter() - start, exc,
            )
            continue
        logger.info("quiz generated on attempt %d (%s) in %.1fs", n, version, time.perf_counter() - start)
        return content
    raise BizError(ErrorCode.QUIZ_GENERATE_FAILED, MSG_GENERATE_FAILED)
