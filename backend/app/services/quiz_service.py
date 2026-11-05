"""出题服务：清洗 → 敏感词 → 联网检索参考资料（可选，尽力而为）→ LangChain 出题 → 校验规范化 → 输出敏感词 → 失败换保守 Prompt 重试。"""

import logging
import time

import openai

from app.core.config import Settings
from app.core.exceptions import BizError, ErrorCode
from app.llm.quiz_chain import QuizGenerator
from app.models.quiz import Quiz, QuizContent, QuizGenerateRequest
from app.prompts.quiz_prompt import CONSERVATIVE_QUIZ_PROMPT, DEFAULT_QUIZ_PROMPT
from app.services.quiz_validator import QuizValidationError, normalize_quiz
from app.services.web_search import WebSearcher, WebSearchError, build_reference
from app.utils.content_filter import ContentFilter
from app.utils.id_generator import new_quiz_id
from app.utils.text_cleaner import clean_text, visible_length

logger = logging.getLogger(__name__)

MSG_TOO_SHORT = "内容太短，AI 猜不出你想学哪方面。至少写 4 个字，比如“RAG 是怎么工作的”。"
MSG_NOT_ALLOWED = "这段内容涉及不适合出题的话题，换个主题试试。"
MSG_GENERATE_FAILED = "题库生成失败，请稍后重试"

# 这些错误换 Prompt 重试也没用（Key 错误、权限、请求参数错误）
_NON_RETRYABLE = (openai.AuthenticationError, openai.PermissionDeniedError, openai.BadRequestError)

# 检索查询词只取清洗后学习内容的前 N 个字：长文本作查询会降低相关度，也少发一些用户内容给第三方
SEARCH_QUERY_MAX_CHARS = 400


def quiz_texts(content: QuizContent) -> list[str]:
    texts = [content.title, content.summary]
    for q in content.questions:
        texts += [q.stem, q.explanation, q.knowledge_point, *(o.text for o in q.options)]
    return texts


class QuizService:
    def __init__(
        self,
        generator: QuizGenerator,
        *,
        settings: Settings,
        content_filter: ContentFilter,
        searcher: WebSearcher | None = None,
    ):
        self._generator = generator
        self._settings = settings
        self._filter = content_filter
        self._searcher = searcher

    def _check_input(self, req: QuizGenerateRequest) -> str:
        text = clean_text(req.user_input)
        if visible_length(text) < self._settings.input_min_chars:
            raise BizError(ErrorCode.INPUT_TOO_SHORT, MSG_TOO_SHORT)
        if self._filter.find(text):
            raise BizError(ErrorCode.CONTENT_NOT_ALLOWED, MSG_NOT_ALLOWED)
        return text

    async def _reference(self, text: str) -> str:
        """检索一次并整理为参考资料；没有 searcher 或任何失败都返回空串，不影响出题。"""
        if self._searcher is None:
            return ""
        start = time.perf_counter()
        try:
            snippets = await self._searcher.search(text[:SEARCH_QUERY_MAX_CHARS])
            reference = build_reference(
                snippets,
                item_max_chars=self._settings.web_reference_item_max_chars,
                total_max_chars=self._settings.web_reference_max_chars,
                content_filter=self._filter,
            )
        except WebSearchError as exc:
            logger.warning(
                "web search failed (status=%s) after %.1fs, quiz continues without reference: %s",
                exc.status, time.perf_counter() - start, exc,
            )
            return ""
        except Exception as exc:  # noqa: BLE001 —— 检索是尽力而为，任何异常都降级
            logger.warning(
                "web search error after %.1fs, quiz continues without reference: %s",
                time.perf_counter() - start, type(exc).__name__,
            )
            return ""
        logger.info(
            "web search ok: %d results, reference %d chars, %.1fs",
            len(snippets), len(reference), time.perf_counter() - start,
        )
        return reference

    async def generate(self, req: QuizGenerateRequest) -> Quiz:
        text = self._check_input(req)
        # 每次出题只检索一次，换保守 Prompt 重试时复用同一份参考资料
        reference = await self._reference(text)
        attempts = self._settings.quiz_max_attempts
        for attempt in range(1, attempts + 1):
            version = DEFAULT_QUIZ_PROMPT if attempt == 1 else CONSERVATIVE_QUIZ_PROMPT
            start = time.perf_counter()
            try:
                generated = await self._generator.generate(
                    user_input=text,
                    question_count=req.question_count,
                    difficulty=req.difficulty,
                    prompt_version=version,
                    reference=reference,
                )
                content = normalize_quiz(generated, req.question_count)
                hit = next((w for t in quiz_texts(content) if (w := self._filter.find(t))), None)
                if hit:
                    raise QuizValidationError(f"generated content hit sensitive word {hit!r}")
            except _NON_RETRYABLE as exc:
                logger.error("quiz generation aborted (non-retryable): %r", exc)
                raise BizError(ErrorCode.QUIZ_GENERATE_FAILED, MSG_GENERATE_FAILED) from exc
            except Exception as exc:  # noqa: BLE001 —— 结构化失败、超时、网络错误都换 Prompt 重试
                logger.warning(
                    "quiz attempt %d/%d (%s) failed after %.1fs: %r",
                    attempt, attempts, version, time.perf_counter() - start, exc,
                )
                continue
            logger.info("quiz generated on attempt %d (%s) in %.1fs", attempt, version, time.perf_counter() - start)
            return Quiz(quiz_id=new_quiz_id(), user_input=text, **content.model_dump())
        raise BizError(ErrorCode.QUIZ_GENERATE_FAILED, MSG_GENERATE_FAILED)
