"""资料后台处理（yhyd_test + 假 Embedder + 内存向量库）。"""

import asyncio
from pathlib import Path

import pytest

from app.core.db import Database
from app.rag.embedding import EmbeddingError
from app.rag.parsing import REASON_BROKEN, REASON_SCANNED, reason_too_long
from app.rag.vector_store import InMemoryVectorStore
from app.services.kb_ingest import REASON_EMBEDDING, REASON_UNKNOWN, KbIngestor
from app.services.kb_service import KbService
from app.utils.content_filter import ContentFilter
from tests.conftest import db_settings
from tests.kb_files import FakeEmbedder, make_pdf, page_text


class Ctx:
    def __init__(self, db, service, ingestor, embedder, vectors, sql, tmp_path: Path):
        self.db, self.service, self.ingestor = db, service, ingestor
        self.embedder, self.vectors, self.sql, self.tmp = embedder, vectors, sql, tmp_path

    async def upload(self, path: Path, file_type: str) -> tuple[str, str]:
        kb = await self.service.create(1, "甲")
        doc = await self.service.add_document(
            1, kb.kb_id, filename=path.name, file_type=file_type, size_bytes=path.stat().st_size
        )
        return kb.kb_id, doc.document_id

    async def run(self, path: Path, file_type: str) -> tuple[str, str, str]:
        kb_id, document_id = await self.upload(path, file_type)
        result = await self.ingestor.process(
            document_id=document_id, user_id=1, kb_id=kb_id, path=path, file_type=file_type
        )
        return kb_id, document_id, result

    def doc(self, document_id: str) -> dict | None:
        return self.sql.one("SELECT * FROM kb_documents WHERE document_id = %s", (document_id,))

    def chunks(self, document_id: str) -> list[dict]:
        return self.sql.all("SELECT * FROM kb_chunks WHERE document_id = %s ORDER BY seq", (document_id,))


@pytest.fixture
async def ctx(sql, tmp_path):
    settings = db_settings(kb_chunk_chars=120, kb_chunk_overlap=20, kb_max_chars=5000)
    db = await Database.connect(settings)
    vectors = InMemoryVectorStore()
    embedder = FakeEmbedder()
    words = ContentFilter(["制毒"])
    service = KbService(db, settings=settings, content_filter=words, vector_store=vectors)
    ingestor = KbIngestor(db, settings=settings, embedder=embedder, vector_store=vectors, content_filter=words)
    yield Ctx(db, service, ingestor, embedder, vectors, sql, tmp_path)
    await ingestor.aclose()
    await db.close()


async def test_pdf_becomes_ready_with_pages_chars_and_chunks(ctx):
    path = make_pdf(ctx.tmp / "manual.pdf", [page_text(i) for i in range(1, 10)])
    _, document_id, result = await ctx.run(path, "pdf")
    assert result == "ready"
    doc = ctx.doc(document_id)
    assert doc["status"] == "ready" and doc["fail_reason"] is None
    assert doc["page_count"] == 9
    assert doc["char_count"] > 0
    chunks = ctx.chunks(document_id)
    assert doc["chunk_count"] == len(chunks) >= 9
    assert [c["seq"] for c in chunks] == list(range(len(chunks)))
    assert {c["page"] for c in chunks} == set(range(1, 10))
    # 向量 id 就是 kb_chunks.id，metadata 带资料与页码
    assert set(ctx.vectors.vectors) == {c["id"] for c in chunks}
    _, meta = ctx.vectors.vectors[chunks[0]["id"]]
    assert (meta.user_id, meta.document_id, meta.page) == (1, document_id, chunks[0]["page"])
    # 原始文件已删除
    assert not path.exists()


async def test_text_file_has_no_pages(ctx):
    path = ctx.tmp / "rules.txt"
    path.write_text("考勤制度：每天九点前打卡。\n\n" * 20, encoding="utf-8")
    _, document_id, result = await ctx.run(path, "txt")
    assert result == "ready"
    assert ctx.doc(document_id)["page_count"] is None
    assert all(c["page"] is None for c in ctx.chunks(document_id))


async def test_sensitive_chunks_are_flagged_but_stored(ctx):
    path = ctx.tmp / "mixed.txt"
    path.write_text("正常的考勤制度内容。\n\n" * 10 + "这里提到了制毒的内容。\n\n" + "正常的报销制度内容。\n\n" * 10, encoding="utf-8")
    _, document_id, result = await ctx.run(path, "txt")
    assert result == "ready"
    chunks = ctx.chunks(document_id)
    flagged = [c for c in chunks if c["flagged"]]
    assert flagged and all("制毒" in c["text"] for c in flagged)
    assert all("制毒" not in c["text"] for c in chunks if not c["flagged"])


async def test_scanned_pdf_fails_with_reason(ctx):
    path = make_pdf(ctx.tmp / "scan.pdf", ["", ""])
    _, document_id, result = await ctx.run(path, "pdf")
    assert result == "failed"
    doc = ctx.doc(document_id)
    assert (doc["status"], doc["fail_reason"]) == ("failed", REASON_SCANNED)
    assert ctx.chunks(document_id) == []
    assert ctx.embedder.calls == []
    assert not path.exists()


async def test_broken_and_too_long_reasons(ctx):
    bad = ctx.tmp / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4\n garbage")
    _, d1, _ = await ctx.run(bad, "pdf")
    assert ctx.doc(d1)["fail_reason"] == REASON_BROKEN
    long = ctx.tmp / "long.txt"
    long.write_text("字" * 5001, encoding="utf-8")
    _, d2, _ = await ctx.run(long, "txt")
    assert ctx.doc(d2)["fail_reason"] == reason_too_long(5000)


async def test_embedding_error_fails_and_leaves_no_vectors(ctx):
    ctx.embedder.error = EmbeddingError("HTTP 503", status=503)
    path = make_pdf(ctx.tmp / "a.pdf", [page_text(1), page_text(2)])
    _, document_id, result = await ctx.run(path, "pdf")
    assert result == "failed"
    doc = ctx.doc(document_id)
    assert (doc["status"], doc["fail_reason"]) == ("failed", REASON_EMBEDDING)
    assert ctx.chunks(document_id) == []
    assert ctx.vectors.count() == 0
    assert not path.exists()


async def test_vector_store_error_rolls_back_chunks(ctx):
    ctx.vectors.fail_next_upsert = RuntimeError("chroma down")
    path = make_pdf(ctx.tmp / "a.pdf", [page_text(1), page_text(2)])
    _, document_id, result = await ctx.run(path, "pdf")
    assert result == "failed"
    assert ctx.doc(document_id)["fail_reason"] == REASON_UNKNOWN
    # upsert 在事务内：失败时片段一起回滚
    assert ctx.chunks(document_id) == []
    assert ctx.vectors.count() == 0


async def test_deleted_while_processing_does_not_come_back(ctx):
    path = make_pdf(ctx.tmp / "a.pdf", [page_text(1), page_text(2)])
    kb_id, document_id = await ctx.upload(path, "pdf")

    async def delete_during_embedding():
        await ctx.service.delete_document(1, kb_id, document_id)

    ctx.embedder.before_return = delete_during_embedding
    result = await ctx.ingestor.process(document_id=document_id, user_id=1, kb_id=kb_id, path=path, file_type="pdf")
    assert result == "deleted"
    assert ctx.doc(document_id) is None
    assert ctx.chunks(document_id) == []
    assert ctx.vectors.count() == 0
    assert not path.exists()


async def test_start_runs_in_background_with_concurrency_limit(ctx):
    paths = []
    for i in range(3):
        p = ctx.tmp / f"{i}.txt"
        p.write_text(f"报销审批规则第 {i} 条。" * 5, encoding="utf-8")
        paths.append(p)
    running = 0
    peak = 0

    async def slow():
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1

    ctx.embedder.before_return = slow
    kb = await ctx.service.create(1, "乙")
    tasks = []
    for p in paths:
        doc = await ctx.service.add_document(1, kb.kb_id, filename=p.name, file_type="txt", size_bytes=10)
        tasks.append(ctx.ingestor.start(document_id=doc.document_id, user_id=1, kb_id=kb.kb_id, path=p, file_type="txt"))
    assert ctx.ingestor.pending == 3
    assert await asyncio.gather(*tasks) == ["ready"] * 3
    assert peak <= 2  # kb_process_concurrency 默认 2
    assert ctx.ingestor.pending == 0


async def test_aclose_cancels_pending_tasks(ctx):
    path = ctx.tmp / "a.txt"
    path.write_text("考勤打卡。" * 10, encoding="utf-8")
    kb_id, document_id = await ctx.upload(path, "txt")

    async def hang():
        await asyncio.sleep(30)

    ctx.embedder.before_return = hang
    ctx.ingestor.start(document_id=document_id, user_id=1, kb_id=kb_id, path=path, file_type="txt")
    await asyncio.sleep(0.05)
    await ctx.ingestor.aclose()
    assert ctx.ingestor.pending == 0
    # 留在 processing，下次启动时由启动恢复标为失败；临时文件已删
    assert ctx.doc(document_id)["status"] == "processing"
    assert not path.exists()
