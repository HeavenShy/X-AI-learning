"""知识库出题的材料选取与出处校验。

取材料（都排除命中敏感词的片段）：
- 填了重点：重点向量化 → 在所选资料里检索 top_k → 按相似度取正文。Embedding / 向量库任何异常都降级为均匀抽取。
- 没填重点：按各资料片段数分配名额（每份至少 1 个），每份资料在片段序列上等距取位置、起点随机偏移，
  所以覆盖前中后、多次出题会变化。不调用 Embedding。
- 按优先级累计到 kb_material_max_chars 为止，再按 资料、seq 排序编号。

出处（attach_sources）：只认本次材料里的编号；去重，最多 3 个。知识库出题 required=True：一题没有有效出处
判为不合格（触发重试）；首页出题 required=False：无效编号只丢弃，该题 sources 为空列表。
摘录：模型给的 source_quote 去空白后是该片段原文的子串就用它，否则取片段开头；都截到 120 字。
"""

import logging
import random
import time
from collections.abc import Sequence

from app.core.config import Settings
from app.core.db import Database
from app.llm.output_schemas import (
    GeneratedKbQuestion,
    GeneratedQuestion,
    GeneratedQuestionWithSources,
    GeneratedQuiz,
)
from app.models.quiz import Question, QuestionSource, QuizContent
from app.prompts.kb_quiz_prompt import MaterialPiece, format_material, strip_tags
from app.rag.embedding import Embedder
from app.rag.vector_store import VectorStore
from app.repositories import kb_repository as kbs
from app.services.quiz_validator import QuizValidationError
from app.utils.text_cleaner import clean_text, visible_length

logger = logging.getLogger(__name__)

MAX_SOURCES = 3
QUOTE_MAX_CHARS = 120
# 模型摘录太短（如一两个字）时不采用，改用片段开头
QUOTE_MIN_CHARS = 4
_SEPARATOR = "\n\n"


# ---------- 取材料 ----------


def spread_positions(positions: Sequence[int], k: int, rng: random.Random) -> list[int]:
    """在有序位置序列上等距取 k 个，起点随机偏移。"""
    n = len(positions)
    k = min(k, n)
    if k <= 0:
        return []
    step = n / k
    offset = rng.random() * step
    picked = {min(n - 1, int(offset + i * step)) for i in range(k)}
    return [positions[i] for i in sorted(picked)]


def allocate_quota(sizes: dict[str, int], total: int) -> dict[str, int]:
    """按片段数比例分配名额，每份有片段的资料至少 1 个，且不超过它的片段数。"""
    docs = [d for d, n in sizes.items() if n > 0]
    if not docs:
        return {}
    all_chunks = sum(sizes[d] for d in docs)
    # 按比例（最大余数法），每份至少 1 个；因“至少 1 个”多出来的名额从名额最多的资料里扣回
    ideal = {d: total * sizes[d] / all_chunks for d in docs}
    quota = {d: max(1, int(ideal[d])) for d in docs}
    leftover = total - sum(quota.values())
    for d in sorted(docs, key=lambda d: ideal[d] - int(ideal[d]), reverse=True)[: max(0, leftover)]:
        quota[d] += 1
    while leftover < 0:
        d = max(docs, key=lambda d: quota[d])
        if quota[d] <= 1:
            break
        quota[d] -= 1
        leftover += 1
    return {d: min(q, sizes[d]) for d, q in quota.items()}


def round_robin(rows_by_doc: dict[str, list[dict]], doc_order: Sequence[str]) -> list[dict]:
    """各资料轮流取一个，用作均匀抽取时的截断优先级：截断也不会把后面的资料整份挤掉。"""
    queues = [list(rows_by_doc.get(d, [])) for d in doc_order]
    out: list[dict] = []
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    return out


def fit_materials(
    rows: Sequence[dict], *, names: dict[str, str], doc_order: Sequence[str], max_chars: int
) -> list[MaterialPiece]:
    """rows 按优先级排列；累计到 max_chars 为止，再按 资料、seq 排序并编号。最终拼接长度不超过 max_chars。"""
    rank = {d: i for i, d in enumerate(doc_order)}

    def build(selected: list[dict]) -> list[MaterialPiece]:
        ordered = sorted(selected, key=lambda r: (rank.get(r["document_id"], len(rank)), r["seq"]))
        return [
            MaterialPiece(
                number=i,
                chunk_id=int(r["id"]),
                document_id=r["document_id"],
                document_name=names.get(r["document_id"], ""),
                page=r["page"],
                text=r["text"],
            )
            for i, r in enumerate(ordered, start=1)
        ]

    def total_len(pieces: list[MaterialPiece]) -> int:
        return sum(len(format_material(p)) for p in pieces) + len(_SEPARATOR) * max(0, len(pieces) - 1)

    selected: list[dict] = []
    for row in rows:
        if total_len(build(selected + [row])) <= max_chars:
            selected.append(row)
    if not selected and rows:
        # 连一个片段都放不下（上限设得比片段还短）：截断第一个片段
        first = dict(rows[0])
        overhead = len(format_material(build([{**first, "text": ""}])[0]))
        first["text"] = first["text"][: max(0, max_chars - overhead)]
        selected = [first]
    return build(selected)


async def retrieve_chunks(
    db: Database,
    *,
    user_id: int,
    document_ids: Sequence[str],
    query: str,
    embedder: Embedder,
    vector_store: VectorStore,
    top_k: int,
) -> list[dict]:
    """查询词 → 向量检索（限定用户与资料）→ 从 kb_chunks 取正文（排除 flagged），按相似度排序。

    返回行含 id、document_id、seq、page、text。异常（Embedding / 向量库 / 数据库）原样抛出，由调用方决定怎么降级。
    知识库出题的固定取材和检索规划 Agent 的知识库工具共用这个函数。
    """
    start = time.perf_counter()
    document_ids = list(document_ids)
    vector = (await embedder.embed([query]))[0]
    chunk_ids = await vector_store.query(vector, user_id=user_id, document_ids=document_ids, top_k=top_k)
    async with db.transaction() as cur:
        rows = await kbs.get_chunks_by_ids(cur, user_id, chunk_ids, document_ids)
    logger.info("kb retrieve: %d hits, %d usable, %.1fs", len(chunk_ids), len(rows), time.perf_counter() - start)
    return rows


def pieces_from_chunks(chunks: Sequence, *, max_chars: int) -> list[MaterialPiece]:
    """检索规划 Agent 查到的片段（KbChunk，按首次命中顺序）→ 编号的材料，截到 max_chars。"""
    rows = [
        {"id": c.id, "document_id": c.document_id, "seq": c.seq, "page": c.page, "text": c.text} for c in chunks
    ]
    names = {c.document_id: c.document_name for c in chunks}
    doc_order = list(dict.fromkeys(c.document_id for c in chunks))
    return fit_materials(rows, names=names, doc_order=doc_order, max_chars=max_chars)


async def _spread(
    db: Database, *, user_id: int, document_ids: list[str], quota_total: int, rng: random.Random
) -> list[dict]:
    async with db.transaction() as cur:
        positions = await kbs.list_chunk_positions(cur, user_id, document_ids)
        quota = allocate_quota({d: len(p) for d, p in positions.items()}, quota_total)
        picks = {d: spread_positions(positions[d], k, rng) for d, k in quota.items()}
        rows = await kbs.get_chunks_by_seq(cur, user_id, picks)
    by_doc: dict[str, list[dict]] = {}
    for r in rows:
        by_doc.setdefault(r["document_id"], []).append(r)
    return round_robin(by_doc, document_ids)


async def select_materials(
    db: Database,
    *,
    user_id: int,
    documents: Sequence[dict],
    focus: str,
    embedder: Embedder | None,
    vector_store: VectorStore | None,
    settings: Settings,
    rng: random.Random | None = None,
) -> list[MaterialPiece]:
    """documents：所选的 ready 资料（document_id、filename），按展示顺序。"""
    rng = rng or random.Random()
    document_ids = [d["document_id"] for d in documents]
    names = {d["document_id"]: d["filename"] for d in documents}
    rows: list[dict] = []
    mode = "spread"
    if focus and embedder is not None and vector_store is not None:
        try:
            rows = await retrieve_chunks(
                db,
                user_id=user_id,
                document_ids=document_ids,
                query=focus,
                embedder=embedder,
                vector_store=vector_store,
                top_k=settings.kb_retrieve_top_k,
            )
            mode = "retrieve"
        except Exception as exc:  # noqa: BLE001 —— 检索失败降级为均匀抽取，照常出题
            logger.warning("kb retrieve failed, fall back to spread sampling: %s", type(exc).__name__)
            rows = []
    if not rows:
        mode = "spread"
        quota_total = max(1, settings.kb_material_max_chars // max(1, settings.kb_chunk_chars))
        rows = await _spread(db, user_id=user_id, document_ids=document_ids, quota_total=quota_total, rng=rng)
    pieces = fit_materials(rows, names=names, doc_order=document_ids, max_chars=settings.kb_material_max_chars)
    logger.info(
        "kb materials (%s): %d pieces from %d documents",
        mode, len(pieces), len({p.document_id for p in pieces}),
    )
    return pieces


# ---------- 出处 ----------


def _squash(text: str) -> str:
    return "".join(clean_text(strip_tags(text)).split())


def _quote_for(piece: MaterialPiece, model_quote: str) -> str:
    quote = clean_text(model_quote or "").strip()
    if visible_length(quote) >= QUOTE_MIN_CHARS and _squash(quote) in _squash(piece.text):
        return quote[:QUOTE_MAX_CHARS]
    return piece.text.strip()[:QUOTE_MAX_CHARS]


_SOURCE_FIELDS = {"source_ids", "source_quote"}


def strip_sources(
    title: str, summary: str, questions: Sequence[GeneratedQuestion], *, topic: str = ""
) -> GeneratedQuiz:
    """去掉题目里的 source_ids / source_quote，得到交给 normalize_quiz 的普通题库。"""
    return GeneratedQuiz(
        title=title,
        summary=summary,
        topic=topic,
        questions=[GeneratedQuestion.model_validate(q.model_dump(exclude=_SOURCE_FIELDS)) for q in questions],
    )


def attach_sources(
    content: QuizContent,
    generated: Sequence[GeneratedKbQuestion | GeneratedQuestionWithSources],
    pieces: Sequence[MaterialPiece],
    *,
    required: bool = True,
) -> QuizContent:
    """把模型标的出处编号对回本次材料，生成每题的 sources。content 与 generated 按题序一一对应。"""
    if len(content.questions) != len(generated):
        raise QuizValidationError("question count mismatch when attaching sources")
    by_number = {p.number: p for p in pieces}
    questions: list[Question] = []
    for q, g in zip(content.questions, generated):
        numbers = list(dict.fromkeys(n for n in g.source_ids if n in by_number))[:MAX_SOURCES]
        if not numbers and required:
            raise QuizValidationError(f"{q.id}: no valid source ids in {g.source_ids}")
        sources = [
            QuestionSource(
                document_id=by_number[n].document_id,
                document_name=by_number[n].document_name,
                page=by_number[n].page,
                quote=_quote_for(by_number[n], g.source_quote),
            )
            for n in numbers
        ]
        questions.append(q.model_copy(update={"sources": sources}))
    return content.model_copy(update={"questions": questions})
