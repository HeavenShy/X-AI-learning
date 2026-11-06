"""知识库 SQL（连 yhyd_test）：用户隔离、排序、计数、删除级联、启动恢复。"""

from datetime import datetime, timedelta

import pytest

from app.core.db import Database
from app.repositories import kb_repository as kbs
from app.repositories.kb_repository import NewChunk
from tests.conftest import db_settings

T0 = datetime(2026, 11, 1, 2, 0, 0)


@pytest.fixture
async def db(sql):
    database = await Database.connect(db_settings())
    yield database
    await database.close()


async def add_kb(db, user_id: int, kb_id: str, name: str = "库", now: datetime = T0):
    async with db.transaction() as cur:
        await kbs.insert_kb(cur, kb_id=kb_id, user_id=user_id, name=name, now=now)


async def add_doc(db, user_id: int, kb_id: str, document_id: str, now: datetime = T0, status: str = "processing"):
    async with db.transaction() as cur:
        await kbs.insert_document(
            cur, document_id=document_id, kb_id=kb_id, user_id=user_id, filename=f"{document_id}.pdf",
            file_type="pdf", size_bytes=100, now=now,
        )
        if status == "ready":
            await kbs.mark_ready(cur, document_id, page_count=2, char_count=10, chunk_count=1)
        elif status == "failed":
            await kbs.mark_failed(cur, document_id, "坏了")


async def test_kb_crud_is_isolated_by_user(db):
    await add_kb(db, 1, "kb_a", "甲")
    await add_kb(db, 2, "kb_b", "乙")
    async with db.transaction() as cur:
        assert (await kbs.get_kb(cur, 1, "kb_a"))["name"] == "甲"
        assert await kbs.get_kb(cur, 2, "kb_a") is None
        assert await kbs.rename_kb(cur, 2, "kb_a", "偷改", T0) is False
        assert await kbs.rename_kb(cur, 1, "kb_a", "甲2", T0) is True
        assert await kbs.delete_kb(cur, 2, "kb_a") is None
        assert [r["kb_id"] for r in await kbs.list_kbs(cur, 1)] == ["kb_a"]
        assert await kbs.count_kbs(cur, 1) == 1
        assert (await kbs.get_kb(cur, 1, "kb_a"))["name"] == "甲2"


async def test_list_kbs_newest_first_with_counts(db):
    await add_kb(db, 1, "kb_old", now=T0)
    await add_kb(db, 1, "kb_new", now=T0 + timedelta(hours=1))
    await add_doc(db, 1, "kb_old", "doc_1", status="ready")
    await add_doc(db, 1, "kb_old", "doc_2", status="failed")
    await add_doc(db, 1, "kb_old", "doc_3")
    await add_doc(db, 1, "kb_new", "doc_4", status="ready")
    async with db.transaction() as cur:
        rows = await kbs.list_kbs(cur, 1)
        assert [r["kb_id"] for r in rows] == ["kb_new", "kb_old"]
        assert [(int(r["document_count"]), int(r["ready_count"])) for r in rows] == [(1, 1), (3, 1)]
        assert await kbs.count_documents(cur, 1) == 4
        assert await kbs.count_documents(cur, 2) == 0
        # 上传会刷新知识库更新时间，排序随之变化
        await kbs.touch_kb(cur, "kb_old", T0 + timedelta(hours=2))
        assert [r["kb_id"] for r in await kbs.list_kbs(cur, 1)] == ["kb_old", "kb_new"]


async def test_documents_newest_first_and_isolated(db):
    await add_kb(db, 1, "kb_a")
    await add_doc(db, 1, "kb_a", "doc_1", now=T0)
    await add_doc(db, 1, "kb_a", "doc_2", now=T0 + timedelta(minutes=1))
    async with db.transaction() as cur:
        docs = await kbs.list_documents(cur, 1, "kb_a")
        assert [d["document_id"] for d in docs] == ["doc_2", "doc_1"]
        assert docs[0]["status"] == "processing" and docs[0]["fail_reason"] is None
        assert await kbs.list_documents(cur, 2, "kb_a") == []
        assert await kbs.get_document(cur, 2, "kb_a", "doc_1") is None
        assert await kbs.get_document(cur, 1, "kb_other", "doc_1") is None
        assert (await kbs.get_document(cur, 1, "kb_a", "doc_1"))["filename"] == "doc_1.pdf"
        assert await kbs.delete_document(cur, 2, "kb_a", "doc_1") is False


async def test_chunks_insert_and_fetch(db, sql):
    await add_kb(db, 1, "kb_a")
    await add_doc(db, 1, "kb_a", "doc_1")
    chunks = [NewChunk(seq=i, page=i + 1, text=f"片段{i}", flagged=(i == 2)) for i in range(5)]
    async with db.transaction() as cur:
        ids = await kbs.insert_chunks(cur, document_id="doc_1", user_id=1, chunks=chunks)
    assert len(set(ids)) == 5
    stored = {r["id"]: r for r in sql.all("SELECT id, seq, page, text, flagged FROM kb_chunks")}
    assert [stored[i]["seq"] for i in ids] == [0, 1, 2, 3, 4]
    assert stored[ids[2]]["flagged"] == 1
    async with db.transaction() as cur:
        # flagged 的片段不参与出题
        assert await kbs.list_chunk_positions(cur, 1, ["doc_1", "doc_x"]) == {"doc_1": [0, 1, 3, 4], "doc_x": []}
        rows = await kbs.get_chunks_by_seq(cur, 1, {"doc_1": [4, 2, 0]})
        assert [(r["seq"], r["page"], r["text"]) for r in rows] == [(0, 1, "片段0"), (4, 5, "片段4")]
        assert await kbs.get_chunks_by_seq(cur, 2, {"doc_1": [0]}) == []
        # 按 id 取：保持传入顺序；限定用户与资料范围
        rows = await kbs.get_chunks_by_ids(cur, 1, [ids[3], ids[2], ids[0]], ["doc_1"])
        assert [r["seq"] for r in rows] == [3, 0]
        assert await kbs.get_chunks_by_ids(cur, 2, ids, ["doc_1"]) == []
        assert await kbs.get_chunks_by_ids(cur, 1, ids, ["doc_other"]) == []


async def test_delete_document_cascades_chunks(db, sql):
    await add_kb(db, 1, "kb_a")
    await add_doc(db, 1, "kb_a", "doc_1")
    await add_doc(db, 1, "kb_a", "doc_2")
    async with db.transaction() as cur:
        await kbs.insert_chunks(cur, document_id="doc_1", user_id=1, chunks=[NewChunk(0, None, "a")])
        await kbs.insert_chunks(cur, document_id="doc_2", user_id=1, chunks=[NewChunk(0, None, "b")])
        assert await kbs.delete_document(cur, 1, "kb_a", "doc_1") is True
    assert [r["document_id"] for r in sql.all("SELECT document_id FROM kb_documents")] == ["doc_2"]
    assert [r["document_id"] for r in sql.all("SELECT document_id FROM kb_chunks")] == ["doc_2"]


async def test_delete_kb_cascades_documents_and_chunks(db, sql):
    await add_kb(db, 1, "kb_a")
    await add_kb(db, 1, "kb_b")
    await add_doc(db, 1, "kb_a", "doc_1")
    await add_doc(db, 1, "kb_a", "doc_2")
    await add_doc(db, 1, "kb_b", "doc_3")
    async with db.transaction() as cur:
        for d in ("doc_1", "doc_3"):
            await kbs.insert_chunks(cur, document_id=d, user_id=1, chunks=[NewChunk(0, None, d)])
        assert sorted(await kbs.delete_kb(cur, 1, "kb_a")) == ["doc_1", "doc_2"]
        assert await kbs.delete_kb(cur, 1, "kb_a") is None
    assert [r["kb_id"] for r in sql.all("SELECT kb_id FROM knowledge_bases")] == ["kb_b"]
    assert [r["document_id"] for r in sql.all("SELECT document_id FROM kb_documents")] == ["doc_3"]
    assert [r["document_id"] for r in sql.all("SELECT document_id FROM kb_chunks")] == ["doc_3"]


async def test_lock_and_status_transitions(db):
    await add_kb(db, 1, "kb_a")
    await add_doc(db, 1, "kb_a", "doc_1")
    async with db.transaction() as cur:
        assert (await kbs.lock_document(cur, "doc_1"))["status"] == "processing"
        await kbs.mark_ready(cur, "doc_1", page_count=9, char_count=1234, chunk_count=3)
        # 已经 ready 的资料不会被标为失败
        assert await kbs.mark_failed(cur, "doc_1", "x") is False
        doc = await kbs.lock_document(cur, "doc_1")
        assert (doc["status"], doc["page_count"], doc["char_count"], doc["chunk_count"]) == ("ready", 9, 1234, 3)
        assert await kbs.lock_document(cur, "doc_missing") is None
        assert await kbs.mark_failed(cur, "doc_missing", "x") is False


async def test_startup_recovery_fails_processing_documents(db):
    await add_kb(db, 1, "kb_a")
    await add_doc(db, 1, "kb_a", "doc_p1")
    await add_doc(db, 2, "kb_a", "doc_p2")
    await add_doc(db, 1, "kb_a", "doc_ok", status="ready")
    async with db.transaction() as cur:
        assert await kbs.fail_interrupted(cur) == 2
        docs = {d["document_id"]: d for d in await kbs.list_documents(cur, 1, "kb_a")}
    assert docs["doc_p1"]["status"] == "failed"
    assert docs["doc_p1"]["fail_reason"] == "处理被中断，请重新上传"
    assert docs["doc_ok"]["status"] == "ready"
