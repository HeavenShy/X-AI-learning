"""报告服务：统计（确定性）+ AI 复盘内容（总结、建议、金句），失败重试，仍失败返回 4004。"""

import logging
import time

import openai

from app.core.config import Settings
from app.core.exceptions import BizError, ErrorCode
from app.llm.output_schemas import GeneratedReport
from app.llm.report_chain import ReportGenerator
from app.models.report import Report, ReportGenerateRequest
from app.prompts.report_prompt import DEFAULT_REPORT_PROMPT
from app.services.scoring_service import score
from app.utils.content_filter import ContentFilter
from app.utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)

MSG_REPORT_FAILED = "复盘报告生成失败，请稍后重试"
_NON_RETRYABLE = (openai.AuthenticationError, openai.PermissionDeniedError, openai.BadRequestError)


class ReportValidationError(ValueError):
    pass


def _clean_items(items: list[str], limit: int) -> list[str]:
    return [s for s in (i.strip() for i in items) if s][:limit]


def _normalize_ai_content(gen: GeneratedReport) -> GeneratedReport:
    lines = _clean_items(gen.three_line_summary, 3)
    advice = _clean_items(gen.advice, 3)
    quote = gen.share_quote.strip()
    if len(lines) != 3:
        raise ReportValidationError(f"three_line_summary needs 3 lines, got {len(lines)}")
    if not advice:
        raise ReportValidationError("advice is empty")
    if not quote:
        raise ReportValidationError("share_quote is empty")
    return GeneratedReport(three_line_summary=lines, advice=advice, share_quote=quote)


class ReportService:
    def __init__(self, generator: ReportGenerator, *, settings: Settings, content_filter: ContentFilter):
        self._generator = generator
        self._settings = settings
        self._filter = content_filter

    async def generate(self, req: ReportGenerateRequest) -> Report:
        summary = score(req.questions, req.answer_records)
        topic = clean_text(req.topic) or "本话"
        attempts = self._settings.report_max_attempts
        for attempt in range(1, attempts + 1):
            start = time.perf_counter()
            try:
                gen = await self._generator.generate(
                    topic=topic, questions=req.questions, summary=summary, prompt_version=DEFAULT_REPORT_PROMPT
                )
                ai = _normalize_ai_content(gen)
                texts = [*ai.three_line_summary, *ai.advice, ai.share_quote]
                hit = next((w for t in texts if (w := self._filter.find(t))), None)
                if hit:
                    raise ReportValidationError(f"report content hit sensitive word {hit!r}")
            except _NON_RETRYABLE as exc:
                logger.error("report generation aborted (non-retryable): %r", exc)
                raise BizError(ErrorCode.REPORT_GENERATE_FAILED, MSG_REPORT_FAILED) from exc
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "report attempt %d/%d failed after %.1fs: %r", attempt, attempts, time.perf_counter() - start, exc
                )
                continue
            logger.info("report generated on attempt %d in %.1fs", attempt, time.perf_counter() - start)
            return Report(
                accuracy=summary.accuracy,
                correct_count=summary.correct_count,
                total_count=summary.total_count,
                total_duration_ms=summary.total_duration_ms,
                mastered_points=summary.mastered_points,
                weak_points=summary.weak_points,
                knowledge_mastery=summary.knowledge_mastery,
                three_line_summary=ai.three_line_summary,
                advice=ai.advice,
                share_quote=ai.share_quote,
            )
        raise BizError(ErrorCode.REPORT_GENERATE_FAILED, MSG_REPORT_FAILED)
