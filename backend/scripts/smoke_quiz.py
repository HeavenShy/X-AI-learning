"""真模型冒烟：连续出题 N 次，统计结构稳定性（方案 Phase 1 验收：连续 10 次，≥80% 可直接渲染）。

用法（在 backend 目录）：
    python -m scripts.smoke_quiz            # 默认 10 次
    python -m scripts.smoke_quiz -n 20
    python -m scripts.smoke_quiz -n 1 --topic "某个较新的主题" --show   # 打印题目，便于对比
    python -m scripts.smoke_quiz -n 1 --topic "某个较新的主题" --show --no-search

配了 TAVILY_API_KEY 时默认出题前联网检索，每行会打印“检索条数 / 耗时”或失败原因；--no-search 强制关闭。
（这个默认模式按固定规则出题，不跑检索规划 Agent。）

知识库模式（需要 SILICONFLOW_API_KEY、DEEPSEEK_API_KEY 和可用的 MySQL）：
    python -m scripts.smoke_quiz --kb 某份资料.pdf -n 3 --focus "报销审批"
读一份本地资料 → 真 Embedding 入库（嵌入式 Chroma，默认 data/chroma_smoke）→ 真模型出题，
无重点、有重点各出 n 次，打印每次耗时、尝试次数、出处有效率（页码与摘录能在原资料对应页找到）。
数据记在一个专用的冒烟用户下，结束时删除；题目不落库。

检索规划 Agent 模式（需要 DEEPSEEK_API_KEY；联网需要 TAVILY_API_KEY；查库需要 --kb 与知识库配置）：
    python -m scripts.smoke_quiz --agent --kb data/smoke/员工手册.pdf
对一组固定主题（常识 / 较新的产品版本 / 与资料相关的主题各 3 个）首页出题，打印每次 Agent 调用了哪些工具、
轮数、规划耗时、总耗时、出处数；再关掉 Agent 用固定规则跑同一组主题，对比总耗时。--kb-topic 可替换资料相关主题。
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
    """记录检索次数 / 最近一次的条数 / 累计耗时 / 失败原因（异常照常抛出，交给调用方降级）。"""

    def __init__(self, inner):
        self.inner = inner
        self.reset()

    def reset(self):
        self.calls = 0
        self.count: int | None = None
        self.elapsed = 0.0
        self.error: str | None = None

    async def search(self, query: str):
        self.calls += 1
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
            self.elapsed += time.perf_counter() - start
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


SMOKE_USER_ID = 4_000_000_001


def _squash(text: str) -> str:
    from app.utils.text_cleaner import clean_text

    return "".join(clean_text(text.replace("<", "").replace(">", "")).split())


class SmokeKb:
    """冒烟用的知识库：专用用户下建一个库、真 Embedding 入库一份本地资料；close() 删除并释放资源。"""

    def __init__(self):
        self.db = None
        self.kb = None

    async def open(self, path: str, chroma_path: str) -> bool:
        import shutil
        from pathlib import Path

        from app.core.db import Database, init_schema
        from app.rag.embedding import SiliconFlowEmbedder
        from app.rag.parsing import detect_file_type
        from app.rag.vector_store import ChromaVectorStore
        from app.services.kb_ingest import KbIngestor
        from app.services.kb_service import KbService

        s = get_settings()
        src = Path(path)
        file_type = detect_file_type(src.name, src)
        if file_type is None:
            print(f"不支持的文件：{src}")
            return False
        self.db = await Database.connect(s)
        await init_schema(self.db)
        self.filter = get_content_filter()
        self.embedder = SiliconFlowEmbedder(s)
        Path(chroma_path).mkdir(parents=True, exist_ok=True)
        self.vectors = ChromaVectorStore(chroma_path, model=s.embedding_model)
        self.kb_service = KbService(self.db, settings=s, content_filter=self.filter, vector_store=self.vectors)
        self.ingestor = KbIngestor(
            self.db, settings=s, embedder=self.embedder, vector_store=self.vectors, content_filter=self.filter
        )
        # 清掉上次冒烟中断时留下的数据
        for kb in (await self.kb_service.list_all(SMOKE_USER_ID)).items:
            await self.kb_service.delete(SMOKE_USER_ID, kb.kb_id)

        self.kb = await self.kb_service.create(SMOKE_USER_ID, "冒烟测试")
        doc = await self.kb_service.add_document(
            SMOKE_USER_ID, self.kb.kb_id, filename=src.name, file_type=file_type, size_bytes=src.stat().st_size
        )
        work = Path(s.kb_upload_dir)
        work.mkdir(parents=True, exist_ok=True)
        tmp = work / f"{doc.document_id}.{file_type}"
        shutil.copyfile(src, tmp)  # 处理结束会删除临时文件，不动原文件
        start = time.perf_counter()
        result = await self.ingestor.process(
            document_id=doc.document_id, user_id=SMOKE_USER_ID, kb_id=self.kb.kb_id, path=tmp, file_type=file_type
        )
        detail = (await self.kb_service.detail(SMOKE_USER_ID, self.kb.kb_id)).documents[0]
        print(
            f"入库 {result}  {time.perf_counter() - start:.1f}s  页数 {detail.page_count}  字数 {detail.char_count}"
            f"  {detail.fail_reason or ''}"
        )
        return result == "ready"

    async def close(self) -> None:
        if self.db is None:
            return
        if self.kb is not None:
            await self.kb_service.delete(SMOKE_USER_ID, self.kb.kb_id)
        await self.ingestor.aclose()
        await self.embedder.aclose()
        self.vectors.close()
        await self.db.close()


async def main_kb(path: str, n: int, *, focus: str, chroma_path: str, show: bool = False) -> int:
    from pathlib import Path

    from app.api.deps import get_kb_quiz_generator
    from app.models.kb import KbQuizRequest
    from app.rag.parsing import detect_file_type, parse_document
    from app.services.kb_quiz_service import KbQuizService

    setup_logging("WARNING")
    s = get_settings()
    if not (s.kb_enabled and s.db_enabled and s.deepseek_api_key):
        print("需要 SILICONFLOW_API_KEY、DEEPSEEK_API_KEY 和 MYSQL_DATABASE")
        return 2
    src = Path(path)
    file_type = detect_file_type(src.name, src)
    if file_type is None:
        print(f"不支持的文件：{src}")
        return 2
    # 原资料按页的文字，用来核对出处
    original = parse_document(src, file_type, max_chars=s.kb_max_chars)
    pages = {seg.page: _squash(seg.text) for seg in original.segments}
    whole = _squash("".join(seg.text for seg in original.segments))

    smoke = SmokeKb()
    try:
        if not await smoke.open(path, chroma_path):
            return 1
        kb = smoke.kb
        counter = CountingGenerator(get_kb_quiz_generator())
        # 这个模式按固定规则取材（不传 planner），与 add-knowledge-base-rag 的冒烟结果可比
        quiz_service = KbQuizService(
            smoke.db, counter, settings=s, content_filter=smoke.filter, embedder=smoke.embedder,
            vector_store=smoke.vectors,
        )

        ok = total_sources = valid_sources = 0
        durations: list[float] = []
        runs = [("", i) for i in range(n)] + [(focus, i) for i in range(n)] if focus else [("", i) for i in range(n)]
        for k, (f, _) in enumerate(runs, start=1):
            counter.calls = 0
            start = time.perf_counter()
            label = f"重点“{f}”" if f else "无重点"
            try:
                quiz = await quiz_service.generate(SMOKE_USER_ID, kb.kb_id, KbQuizRequest(focus=f, question_count=5))
            except BizError as e:
                print(f"[{k:02d}] FAIL  {label}  {time.perf_counter() - start:5.1f}s  -> {e.code} {e.message}")
                continue
            cost = time.perf_counter() - start
            ok += 1
            durations.append(cost)
            bad: list[str] = []
            for q in quiz.questions:
                for src_item in q.sources:
                    total_sources += 1
                    text = pages.get(src_item.page, whole) if src_item.page is not None else whole
                    if _squash(src_item.quote)[:60] in text:
                        valid_sources += 1
                    else:
                        bad.append(f"{q.id} p{src_item.page}")
            pages_used = sorted({s_.page for q in quiz.questions for s_ in q.sources if s_.page is not None})
            print(
                f"[{k:02d}] OK    {label}  {cost:5.1f}s  尝试 {counter.calls} 次  {quiz.title}"
                f"  出处页 {pages_used}{'  无效 ' + ', '.join(bad) if bad else ''}"
            )
            if show:
                for q in quiz.questions:
                    print(f"     - [{q.type}] {q.stem}  答案 {''.join(q.answer)}")
                    for src_item in q.sources:
                        print(f"       出处：{src_item.document_name} 第 {src_item.page} 页：{src_item.quote[:40]}…")
        print("-" * 60)
        print(f"成功 {ok}/{len(runs)}，出处有效 {valid_sources}/{total_sources}")
        if durations:
            print(f"耗时 中位数 {statistics.median(durations):.1f}s，最长 {max(durations):.1f}s")
        return 0 if ok == len(runs) and valid_sources == total_sources else 1
    finally:
        await smoke.close()


# ---------- 检索规划 Agent ----------

AGENT_TOPICS = {
    "常识": ["勾股定理是什么", "为什么天空是蓝色的", "光合作用的过程"],
    "较新版本": ["Python 3.14 有哪些新特性", "Kubernetes 1.34 有哪些主要变化", "iPhone 17 系列有哪些新功能"],
}
# 与 data/smoke/员工手册.pdf 相关；换资料时用 --kb-topic 替换
DEFAULT_KB_TOPICS = ["我们公司的报销审批流程是怎样的", "公司年假天数怎么计算", "公司对员工系统密码有什么要求"]


class RecordingPlanner:
    """记录最近一次规划的结果、耗时与降级原因（异常照常抛出，交给 QuizService 降级）。"""

    def __init__(self, inner):
        self.inner = inner
        self.reset()

    def reset(self):
        self.result = None
        self.elapsed = 0.0
        self.error: str | None = None
        self.called = False

    async def plan(self, ctx):
        from app.agent.retrieval_planner import PlanningError

        self.called = True
        start = time.perf_counter()
        try:
            self.result = await self.inner.plan(ctx)
            return self.result
        except PlanningError as e:
            self.error = e.reason
            raise
        finally:
            self.elapsed = time.perf_counter() - start


def _pct(values: list[float], p: int) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1]


async def main_agent(*, kb_path: str | None, kb_topics: list[str], chroma_path: str, show: bool = False) -> int:
    from app.agent.retrieval_planner import RetrievalPlanner
    from app.api.deps import get_retrieval_llm
    from app.services.kb_retrieval import KbRetriever

    setup_logging("WARNING")
    s = get_settings()
    if not s.deepseek_api_key:
        print("需要 DEEPSEEK_API_KEY")
        return 2
    if kb_path and not (s.kb_enabled and s.db_enabled):
        print("查库需要 SILICONFLOW_API_KEY 和 MYSQL_DATABASE")
        return 2
    filt = get_content_filter()
    searcher = TimingSearcher(TavilySearcher(s)) if s.web_search_enabled else None
    smoke = SmokeKb() if kb_path else None
    topics = dict(AGENT_TOPICS)
    try:
        if smoke is not None:
            if not await smoke.open(kb_path, chroma_path):
                return 1
            topics["资料相关"] = kb_topics
        print(f"联网检索：{'开启' if searcher else '关闭'}  知识库：{'开启' if smoke else '关闭'}")
        planner = RecordingPlanner(RetrievalPlanner(get_retrieval_llm(), settings=s, content_filter=filt))
        settings_for = {
            "agent": s.model_copy(update={"agent_retrieval_enabled": True}),
            "fixed": s.model_copy(update={"agent_retrieval_enabled": False}),
        }
        plan_times: list[float] = []
        totals: dict[str, list[float]] = {"agent": [], "fixed": []}
        failures = 0
        for mode in ("agent", "fixed"):
            print("-" * 60)
            print("检索规划 Agent" if mode == "agent" else "固定规则（关闭 Agent，对比总耗时）")
            for group, items in topics.items():
                for text in items:
                    # 与线上一致：首页的知识库检索执行器每请求组装一次
                    kb = (
                        KbRetriever(
                            smoke.db, user_id=SMOKE_USER_ID, embedder=smoke.embedder, vector_store=smoke.vectors,
                            top_k=s.agent_kb_top_k,
                        )
                        if smoke is not None
                        else None
                    )
                    service = QuizService(
                        get_quiz_generator(),
                        settings=settings_for[mode],
                        content_filter=filt,
                        searcher=searcher,
                        planner=planner if mode == "agent" else None,
                        kb_retriever=kb,
                    )
                    planner.reset()
                    if searcher:
                        searcher.reset()
                    start = time.perf_counter()
                    try:
                        quiz = await service.generate(QuizGenerateRequest(user_input=text, question_count=5))
                    except BizError as e:
                        failures += 1
                        print(f"  FAIL  [{group}] {text}  {time.perf_counter() - start:5.1f}s -> {e.message}")
                        continue
                    total = time.perf_counter() - start
                    totals[mode].append(total)
                    sources = sum(len(q.sources) for q in quiz.questions)
                    with_sources = sum(1 for q in quiz.questions if q.sources)
                    if mode == "agent":
                        r = planner.result
                        if planner.called:
                            plan_times.append(planner.elapsed)
                        if planner.error:
                            plan = f"规划失败 {planner.error}（{planner.elapsed:.1f}s，已降级）"
                        elif r is None:
                            plan = "未规划（无可用数据源）"
                        else:
                            used = ",".join(f"{k}×{v}" for k, v in (("kb", r.kb_calls), ("web", r.web_calls)) if v)
                            plan = f"工具 {used or '无'}  {r.rounds} 轮  规划 {planner.elapsed:4.1f}s"
                    else:
                        plan = searcher.describe() if searcher else "未检索"
                    print(
                        f"  [{group}] {text}  {plan}  总 {total:4.1f}s  出处 {sources}（{with_sources} 题）"
                        f"  {quiz.source_type}  {quiz.title}"
                    )
                    if show:
                        for q in quiz.questions:
                            print(f"     - [{q.type}] {q.stem}  答案 {''.join(q.answer)}")
                            for src in q.sources:
                                print(f"       出处：{src.document_name} 第 {src.page} 页：{src.quote[:40]}…")
        print("-" * 60)
        if plan_times:
            print(
                f"规划耗时 P50 {_pct(plan_times, 50):.1f}s  P90 {_pct(plan_times, 90):.1f}s  "
                f"最长 {max(plan_times):.1f}s（{len(plan_times)} 次）"
            )
        for mode, label in (("agent", "Agent"), ("fixed", "固定规则")):
            if totals[mode]:
                print(
                    f"{label} 总耗时 中位数 {statistics.median(totals[mode]):.1f}s  "
                    f"P90 {_pct(totals[mode], 90):.1f}s  最长 {max(totals[mode]):.1f}s"
                )
        return 0 if failures == 0 else 1
    finally:
        if searcher:
            await searcher.inner.aclose()
        if smoke is not None:
            await smoke.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=10)
    parser.add_argument("--no-search", action="store_true", help="即使配了 TAVILY_API_KEY 也不联网检索")
    parser.add_argument("--topic", help="只用这一个学习内容出题（5 题）")
    parser.add_argument("--show", action="store_true", help="打印每套题的题干、选项和答案")
    parser.add_argument("--kb", metavar="FILE", help="知识库模式：用这份本地资料（pdf / docx / txt / md）出题")
    parser.add_argument("--focus", default="", help="知识库模式：另外用这个重点再出 n 次")
    parser.add_argument("--chroma", default="data/chroma_smoke", help="知识库模式：冒烟用的 Chroma 目录")
    parser.add_argument("--agent", action="store_true", help="检索规划 Agent 模式：固定主题集，统计工具选择与耗时")
    parser.add_argument("--kb-topic", action="append", help="Agent 模式：与 --kb 资料相关的主题（可重复，替换默认 3 个）")
    args = parser.parse_args()
    if args.agent:
        sys.exit(
            asyncio.run(
                main_agent(
                    kb_path=args.kb,
                    kb_topics=args.kb_topic or DEFAULT_KB_TOPICS,
                    chroma_path=args.chroma,
                    show=args.show,
                )
            )
        )
    if args.kb:
        sys.exit(asyncio.run(main_kb(args.kb, args.n, focus=args.focus, chroma_path=args.chroma, show=args.show)))
    sys.exit(asyncio.run(main(args.n, search=not args.no_search, topic=args.topic, show=args.show)))
