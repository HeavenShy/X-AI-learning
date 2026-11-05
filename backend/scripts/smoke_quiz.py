"""真模型冒烟：连续出题 N 次，统计结构稳定性（方案 Phase 1 验收：连续 10 次，≥80% 可直接渲染）。

用法（在 backend 目录）：
    python -m scripts.smoke_quiz            # 默认 10 次
    python -m scripts.smoke_quiz -n 20
    python -m scripts.smoke_quiz -n 1 --topic "某个较新的主题" --show   # 打印题目，便于对比
    python -m scripts.smoke_quiz -n 1 --topic "某个较新的主题" --show --no-search

配了 TAVILY_API_KEY 时默认出题前联网检索，每行会打印“检索条数 / 耗时”或失败原因；--no-search 强制关闭。
"""

import argparse
import asyncio
import statistics
import sys
import time
from collections import Counter

from app.api.deps import get_quiz_generator, get_report_service
from app.core.config import get_settings
from app.core.exceptions import BizError
from app.core.logging import setup_logging
from app.models.quiz import QuizGenerateRequest
from app.models.report import AnswerRecord, ReportGenerateRequest
from app.services.quiz_service import QuizService
from app.services.web_search import TavilySearcher, WebSearchError
from app.utils.content_filter import get_content_filter

CASES = [
    ("我想学习什么是 RAG，以及它和传统搜索有什么区别", 5),
    ("复利是怎么算的", 3),
    ("咖啡因为什么提神", 5),
    ("碳中和是什么意思", 10),
    ("TCP 三次握手为什么不是两次", 5),
    ("光合作用的过程", 3),
    ("《红楼梦》里贾宝玉和林黛玉的关系", 5),
    ("Python 的列表和元组有什么区别", 10),
    ("通货膨胀对普通人的影响", 5),
    ("为什么天空是蓝色的", 3),
]


class CountingGenerator:
    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        return await self.inner.generate(**kwargs)


class TimingSearcher:
    """记录最近一次检索的条数 / 耗时 / 失败原因（异常照常抛出，交给 QuizService 降级）。"""

    def __init__(self, inner):
        self.inner = inner
        self.reset()

    def reset(self):
        self.count: int | None = None
        self.elapsed = 0.0
        self.error: str | None = None

    async def search(self, query: str):
        start = time.perf_counter()
        try:
            result = await self.inner.search(query)
        except WebSearchError as e:
            self.error = f"HTTP {e.status}" if e.status else str(e)
            raise
        except Exception as e:
            self.error = type(e).__name__
            raise
        finally:
            self.elapsed = time.perf_counter() - start
        self.count = len(result)
        return result

    def describe(self) -> str:
        if self.error:
            return f"检索失败 {self.error}（{self.elapsed:.1f}s，已降级）"
        if self.count is None:
            return "未检索"
        return f"检索 {self.count} 条 {self.elapsed:.1f}s"


async def main(n: int, *, search: bool = True, topic: str | None = None, show: bool = False) -> int:
    setup_logging("WARNING")
    s = get_settings()
    searcher = TimingSearcher(TavilySearcher(s)) if search and s.web_search_enabled else None
    print(f"联网检索：{'开启' if searcher else '关闭'}")
    cases = [(topic, 5)] if topic else CASES
    service = QuizService(get_quiz_generator(), settings=s, content_filter=get_content_filter(), searcher=searcher)
    counter = CountingGenerator(service._generator)  # noqa: SLF001 —— 冒烟脚本专用
    service._generator = counter  # noqa: SLF001

    ok = first_try = 0
    durations: list[float] = []
    single_answers: Counter[str] = Counter()
    last_quiz = None
    for i in range(n):
        text, count = cases[i % len(cases)]
        counter.calls = 0
        if searcher:
            searcher.reset()
        start = time.perf_counter()
        try:
            quiz = await service.generate(QuizGenerateRequest(user_input=text, question_count=count))
        except BizError as e:
            print(f"[{i + 1:02d}] FAIL  {count:>2} 题  {time.perf_counter() - start:5.1f}s  {text}  -> {e.message}")
            continue
        cost = time.perf_counter() - start
        ok += 1
        first_try += counter.calls == 1
        durations.append(cost)
        single_answers.update(q.answer[0] for q in quiz.questions if q.type == "single")
        last_quiz = quiz
        search_info = f"  {searcher.describe()}" if searcher else ""
        print(f"[{i + 1:02d}] OK    {count:>2} 题  {cost:5.1f}s  尝试 {counter.calls} 次{search_info}  {quiz.title}")
        if show:
            for q in quiz.questions:
                opts = "  ".join(f"{o.key}.{o.text}" for o in q.options)
                print(f"     - [{q.type}] {q.stem}")
                print(f"       {opts}  答案 {''.join(q.answer)}")

    print("-" * 60)
    print(f"成功 {ok}/{n}（{ok * 100 // n}%），首次即通过 {first_try}/{n}")
    if durations:
        print(f"耗时 中位数 {statistics.median(durations):.1f}s，最长 {max(durations):.1f}s")
    print(f"单选答案位置分布：{dict(sorted(single_answers.items()))}")

    if last_quiz:
        qs = last_quiz.questions
        records = [
            AnswerRecord(question_id=q.id, selected_answers=list(q.answer) if i % 3 else ["A"], duration_ms=4000)
            for i, q in enumerate(qs)
        ]
        start = time.perf_counter()
        report = await get_report_service().generate(
            ReportGenerateRequest(quiz_id=last_quiz.quiz_id, topic=last_quiz.title, questions=qs, answer_records=records)
        )
        print("-" * 60)
        print(f"报告 {time.perf_counter() - start:.1f}s  正确率 {report.accuracy}%  薄弱 {report.weak_points}")
        for line in report.three_line_summary:
            print("  ·", line)
        print("  建议：", report.advice)
        print("  金句：", report.share_quote)
    if searcher:
        await searcher.inner.aclose()
    return 0 if ok * 100 >= n * 80 else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=10)
    parser.add_argument("--no-search", action="store_true", help="即使配了 TAVILY_API_KEY 也不联网检索")
    parser.add_argument("--topic", help="只用这一个学习内容出题（5 题）")
    parser.add_argument("--show", action="store_true", help="打印每套题的题干、选项和答案")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.n, search=not args.no_search, topic=args.topic, show=args.show)))
