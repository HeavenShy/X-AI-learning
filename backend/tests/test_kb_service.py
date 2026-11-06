"""知识库管理服务（yhyd_test + 内存向量库）：建库、列表、详情、改名、删除、隔离。"""

from datetime import datetime, timedelta

import pytest

from app.core.db import Database
from app.core.exceptions import BizError, ErrorCode
from app.rag.vector_store import InMemoryVectorStore, VectorMeta
from app.repositories import kb_repository as kbs
from app.repositories.kb_repository import NewChunk
from app.services.kb_service import KbService, safe_filename
from app.utils.content_filter import ContentFilter
from tests.conftest import db_settings

T0 = datetime(2026, 11, 1, 2, 0, 0)


class Ctx:
    def __init__(self, db: Database, service: KbService, vectors: InMemoryVectorStore):
        self.db = db
        self.service = service
        self.vectors = vectors

    async def upload(self, user_id: int, kb_id: str, name: str = "a.pdf", status: str = "processing", now=None):
        doc = await self.service.add_document(
            user_id, kb_id, filename=name, file_type="pdf", size_bytes=1000, now=now or T0
        )
        async with self.db.transaction() as cur:
            if status == "ready":
                ids = await kbs.insert_chunks(
                    cur, document_id=doc.document_id, user_id=user_id, chunks=[NewChunk(0, 1, "正文")]
                )
                await kbs.mark_ready(cur, doc.document_id, page_count=1, char_count=2, chunk_count=1)
                await self.vectors.upsert(
                    ids, [[1.0, 0.0]], [VectorMeta(user_id=user_id, kb_id=kb_id, document_id=doc.document_id)]
                )
            elif status == "failed":
                await kbs.mark_failed(cur, doc.document_id, "读不出文字，可能是扫描件或图片版 PDF，请上传文字版")
        return doc.document_id


@pytest.fixture
async def ctx(sql):
    settings = db_settings(kb_max_bases=3, kb_max_documents=4)
    db = await Database.connect(settings)
    vectors = InMemoryVectorStore()
    service = KbService(db, settings=settings, content_filter=ContentFilter(["制毒"]), vector_store=vectors)
    yield Ctx(db, service, vectors)
    await db.close()


async def biz_code(coro) -> int:
    with pytest.raises(BizError) as info:
        await coro
    return info.value.code


# ---------- 建库 ----------


async def test_create_and_list(ctx):
    kb = await ctx.service.create(1, "  公司新人考核 ")
    assert kb.name == "公司新人考核"
    assert kb.kb_id.startswith("kb_")
    assert (kb.document_count, kb.ready_count) == (0, 0)
    assert kb.created_at.endswith("Z")
    page = await ctx.service.list_all(1)
    assert [k.kb_id for k in page.items] == [kb.kb_id]
    assert (page.total, page.document_total, page.document_limit) == (1, 0, 4)


@pytest.mark.parametrize("name", ["", "   \n ", "字" * 21])
async def test_create_rejects_empty_or_long_name(ctx, name):
    assert await biz_code(ctx.service.create(1, name)) == ErrorCode.INVALID_PARAMS
    assert (await ctx.service.list_all(1)).items == []


async def test_create_accepts_twenty_chars(ctx):
    assert (await ctx.service.create(1, "字" * 20)).name == "字" * 20


async def test_create_rejects_sensitive_name(ctx):
    assert await biz_code(ctx.service.create(1, "制 毒手册")) == ErrorCode.CONTENT_NOT_ALLOWED
    assert (await ctx.service.list_all(1)).items == []


async def test_create_limit(ctx):
    for i in range(3):
        await ctx.service.create(1, f"库{i}")
    assert await biz_code(ctx.service.create(1, "再来一个")) == ErrorCode.LIMIT_EXCEEDED
    # 上限按用户计
    await ctx.service.create(2, "别人的库")


# ---------- 列表 / 详情 ----------


async def test_list_counts_and_order(ctx):
    a = await ctx.service.create(1, "甲", now=T0)
    b = await ctx.service.create(1, "乙", now=T0 + timedelta(minutes=1))
    await ctx.upload(1, a.kb_id, "1.pdf", "ready", now=T0 + timedelta(minutes=2))
    await ctx.upload(1, a.kb_id, "2.pdf", "failed", now=T0 + timedelta(minutes=2))
    await ctx.upload(1, a.kb_id, "3.pdf", now=T0 + timedelta(minutes=2))
    await ctx.upload(1, b.kb_id, "4.pdf", now=T0 + timedelta(minutes=1))
    page = await ctx.service.list_all(1)
    # 上传刷新了甲的更新时间，甲排前面
    assert [k.name for k in page.items] == ["甲", "乙"]
    assert [(k.document_count, k.ready_count) for k in page.items] == [(3, 1), (1, 0)]
    assert page.document_total == 4


async def test_list_empty(ctx):
    page = await ctx.service.list_all(1)
    assert (page.items, page.total, page.document_total) == ([], 0, 0)


async def test_detail_shows_documents_newest_first_with_status(ctx):
    kb = await ctx.service.create(1, "甲")
    await ctx.upload(1, kb.kb_id, "ready.pdf", "ready", now=T0)
    await ctx.upload(1, kb.kb_id, "doing.pdf", now=T0 + timedelta(minutes=1))
    await ctx.upload(1, kb.kb_id, "bad.pdf", "failed", now=T0 + timedelta(minutes=2))
    detail = await ctx.service.detail(1, kb.kb_id)
    assert detail.knowledge_base.kb_id == kb.kb_id
    assert [(d.filename, d.status) for d in detail.documents] == [
        ("bad.pdf", "failed"),
        ("doing.pdf", "processing"),
        ("ready.pdf", "ready"),
    ]
    assert detail.documents[0].fail_reason.startswith("读不出文字")
    assert detail.documents[1].fail_reason is None
    assert detail.documents[2].page_count == 1
    assert detail.documents[2].created_at == "2026-11-01T02:00:00Z"


# ---------- 改名 / 删除 ----------


async def test_rename(ctx):
    kb = await ctx.service.create(1, "甲")
    renamed = await ctx.service.rename(1, kb.kb_id, "PMP 备考")
    assert renamed.name == "PMP 备考"
    assert (await ctx.service.detail(1, kb.kb_id)).knowledge_base.name == "PMP 备考"
    assert [k.name for k in (await ctx.service.list_all(1)).items] == ["PMP 备考"]
    assert await biz_code(ctx.service.rename(1, kb.kb_id, "")) == ErrorCode.INVALID_PARAMS
    assert await biz_code(ctx.service.rename(1, kb.kb_id, "制毒")) == ErrorCode.CONTENT_NOT_ALLOWED


async def test_delete_kb_removes_documents_text_and_vectors(ctx, sql):
    kb = await ctx.service.create(1, "甲")
    other = await ctx.service.create(1, "乙")
    for i in range(3):
        await ctx.upload(1, kb.kb_id, f"{i}.pdf", "ready")
    keep = await ctx.upload(1, other.kb_id, "keep.pdf", "ready")
    assert (await ctx.service.list_all(1)).document_total == 4
    await ctx.service.delete(1, kb.kb_id)
    page = await ctx.service.list_all(1)
    assert [k.name for k in page.items] == ["乙"]
    assert page.document_total == 1
    assert ctx.vectors.document_ids() == {keep}
    assert [r["document_id"] for r in sql.all("SELECT document_id FROM kb_chunks")] == [keep]
    assert await biz_code(ctx.service.detail(1, kb.kb_id)) == ErrorCode.NOT_FOUND
    assert await biz_code(ctx.service.delete(1, kb.kb_id)) == ErrorCode.NOT_FOUND


async def test_delete_document(ctx, sql):
    kb = await ctx.service.create(1, "甲")
    gone = await ctx.upload(1, kb.kb_id, "gone.pdf", "ready")
    stay = await ctx.upload(1, kb.kb_id, "stay.pdf", "ready")
    await ctx.service.delete_document(1, kb.kb_id, gone)
    assert [d.document_id for d in (await ctx.service.detail(1, kb.kb_id)).documents] == [stay]
    assert ctx.vectors.document_ids() == {stay}
    assert sql.one("SELECT COUNT(*) AS n FROM kb_chunks WHERE document_id = %s", (gone,))["n"] == 0
    assert await biz_code(ctx.service.delete_document(1, kb.kb_id, gone)) == ErrorCode.NOT_FOUND


async def test_vector_delete_failure_does_not_fail_delete(ctx, caplog):
    kb = await ctx.service.create(1, "甲")
    doc = await ctx.upload(1, kb.kb_id, "a.pdf", "ready")

    async def broken(_ids):
        raise RuntimeError("chroma down")

    ctx.vectors.delete_documents = broken
    await ctx.service.delete_document(1, kb.kb_id, doc)
    assert (await ctx.service.detail(1, kb.kb_id)).documents == []
    assert "delete vectors" in caplog.text


# ---------- 上传登记 ----------


async def test_document_limit_counts_all_bases(ctx):
    a = await ctx.service.create(1, "甲")
    b = await ctx.service.create(1, "乙")
    for i in range(3):
        await ctx.upload(1, a.kb_id, f"{i}.pdf")
    await ctx.upload(1, b.kb_id, "3.pdf", "failed")
    assert await biz_code(ctx.service.check_upload_allowed(1, b.kb_id)) == ErrorCode.LIMIT_EXCEEDED
    assert await biz_code(ctx.upload(1, b.kb_id, "4.pdf")) == ErrorCode.LIMIT_EXCEEDED


def test_safe_filename():
    assert safe_filename("C:\\fakepath\\报销 制度.pdf") == "报销 制度.pdf"
    assert safe_filename("../../etc/passwd.txt") == "passwd.txt"
    assert safe_filename("") == "未命名资料"
    long = safe_filename("长" * 200 + ".docx")
    assert len(long) == 100 and long.endswith(".docx")


# ---------- 隔离 ----------


async def test_other_users_cannot_touch_knowledge_base(ctx):
    kb = await ctx.service.create(1, "A 的库")
    doc = await ctx.upload(1, kb.kb_id, "a.pdf", "ready")
    s = ctx.service
    assert await biz_code(s.detail(2, kb.kb_id)) == ErrorCode.NOT_FOUND
    assert await biz_code(s.rename(2, kb.kb_id, "偷改")) == ErrorCode.NOT_FOUND
    assert await biz_code(s.delete(2, kb.kb_id)) == ErrorCode.NOT_FOUND
    assert await biz_code(s.delete_document(2, kb.kb_id, doc)) == ErrorCode.NOT_FOUND
    assert await biz_code(s.check_upload_allowed(2, kb.kb_id)) == ErrorCode.NOT_FOUND
    assert await biz_code(ctx.upload(2, kb.kb_id)) == ErrorCode.NOT_FOUND
    assert (await s.list_all(2)).items == []
    # A 的数据不变
    detail = await s.detail(1, kb.kb_id)
    assert detail.knowledge_base.name == "A 的库"
    assert [d.document_id for d in detail.documents] == [doc]
    assert ctx.vectors.document_ids() == {doc}


async def test_document_must_belong_to_kb(ctx):
    a = await ctx.service.create(1, "甲")
    b = await ctx.service.create(1, "乙")
    doc = await ctx.upload(1, a.kb_id, "a.pdf")
    assert await biz_code(ctx.service.delete_document(1, b.kb_id, doc)) == ErrorCode.NOT_FOUND
    assert len((await ctx.service.detail(1, a.kb_id)).documents) == 1
