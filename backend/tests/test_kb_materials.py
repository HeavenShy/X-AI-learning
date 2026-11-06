"""出题材料选取（yhyd_test + 假 Embedder + 内存向量库）。"""

import random

import pytest

from app.core.db import Database
from app.prompts.kb_quiz_prompt import format_materials
from app.rag.embedding import EmbeddingError
from app.rag.vector_store import InMemoryVectorStore, VectorMeta
from app.services.kb_materials import allocate_quota, retrieve_chunks, select_materials, spread_positions
from tests.conftest import db_settings
from tests.kb_files import FakeEmbedder, keyword_vector


class Setup:
    def __init__(self, sql, db, vectors, embedder):
        self.sql, self.db, self.vectors, self.embedder = sql, db, vectors, embedder
        self.docs: list[dict] = []

    async def add_doc(self, document_id: str, filename: str, texts: list[str], *, user_id: int = 1, flag=()):
        self.sql.execute(
            "INSERT INTO kb_documents (document_id, kb_id, user_id, filename, file_type, size_bytes, status, "
            "chunk_count) VALUES (%s, 'kb_a', %s, %s, 'txt', 1, 'ready', %s)",
            (document_id, user_id, filename, len(texts)),
        )
        ids, embs, metas = [], [], []
        for seq, text in enumerate(texts):
            cid = self.sql.execute(
                "INSERT INTO kb_chunks (document_id, user_id, seq, page, text, flagged) VALUES (%s, %s, %s, %s, %s, %s)",
                (document_id, user_id, seq, seq + 1, text, int(seq in flag)),
            )
            ids.append(cid)
            embs.append(keyword_vector(text, FakeEmbedder.KEYWORDS))
            metas.append(VectorMeta(user_id=user_id, kb_id="kb_a", document_id=document_id, page=seq + 1))
        await self.vectors.upsert(ids, embs, metas)
        doc = {"document_id": document_id, "filename": filename}
        if user_id == 1:
            self.docs.append(doc)
        return doc

    async def select(self, focus: str = "", *, seed: int = 0, docs=None, **overrides):
        settings = db_settings(**overrides)
        return await select_materials(
            self.db,
            user_id=1,
            documents=docs if docs is not None else self.docs,
            focus=focus,
            embedder=self.embedder,
            vector_store=self.vectors,
            settings=settings,
            rng=random.Random(seed),
        )


@pytest.fixture
async def setup(sql):
    db = await Database.connect(db_settings())
    yield Setup(sql, db, InMemoryVectorStore(), FakeEmbedder())
    await db.close()


def texts(prefix: str, n: int, word: str = "") -> list[str]:
    return [f"{prefix}第{i}段{word}。" + "内容" * 30 for i in range(n)]


# ---------- 纯函数 ----------


def test_spread_positions_cover_front_middle_back():
    picked = spread_positions(list(range(100)), 5, random.Random(0))
    assert len(picked) == 5
    assert picked[0] < 20 and picked[-1] >= 80
    assert spread_positions(list(range(3)), 10, random.Random(0)) == [0, 1, 2]
    assert spread_positions([], 3, random.Random(0)) == []


def test_allocate_quota_proportional_with_minimum_one():
    assert allocate_quota({"a": 90, "b": 10}, 10) == {"a": 9, "b": 1}
    q = allocate_quota({"a": 100, "b": 1, "c": 1}, 12)
    assert q["b"] == 1 and q["c"] == 1 and q["a"] == 10
    # 名额比资料还少时每份仍至少 1 个
    assert allocate_quota({"a": 5, "b": 5, "c": 5}, 2) == {"a": 1, "b": 1, "c": 1}
    assert allocate_quota({"a": 2}, 12) == {"a": 2}
    assert allocate_quota({"a": 0}, 12) == {}


# ---------- 无重点：均匀抽取 ----------


async def test_spread_covers_every_document(setup):
    await setup.add_doc("doc_a", "甲.txt", texts("甲", 30))
    await setup.add_doc("doc_b", "乙.txt", texts("乙", 30))
    await setup.add_doc("doc_c", "丙.txt", texts("丙", 3))
    pieces = await setup.select()
    assert {p.document_id for p in pieces} == {"doc_a", "doc_b", "doc_c"}
    assert setup.embedder.calls == []  # 没填重点不调 Embedding
    # 编号连续，按 资料、seq 排序
    assert [p.number for p in pieces] == list(range(1, len(pieces) + 1))
    order = [(["doc_a", "doc_b", "doc_c"].index(p.document_id), p.page) for p in pieces]
    assert order == sorted(order)
    assert pieces[0].document_name == "甲.txt"


async def test_spread_covers_start_middle_end_of_document(setup):
    await setup.add_doc("doc_a", "甲.txt", texts("甲", 60))
    pieces = await setup.select()
    seqs = [p.page - 1 for p in pieces]
    assert min(seqs) < 20 and max(seqs) >= 40


async def test_spread_changes_between_runs(setup):
    await setup.add_doc("doc_a", "甲.txt", texts("甲", 60))
    first = {p.chunk_id for p in await setup.select(seed=1)}
    second = {p.chunk_id for p in await setup.select(seed=2)}
    assert first != second
    # 同一种子可复现
    assert first == {p.chunk_id for p in await setup.select(seed=1)}


async def test_materials_respect_length_limit(setup):
    await setup.add_doc("doc_a", "甲.txt", texts("甲", 40))
    await setup.add_doc("doc_b", "乙.txt", texts("乙", 40))
    for focus in ("", "甲"):
        pieces = await setup.select(focus, kb_material_max_chars=1000)
        assert len(format_materials(pieces)) <= 1000
        assert pieces
    # 截断后仍覆盖两份资料
    pieces = await setup.select(kb_material_max_chars=1000)
    assert {p.document_id for p in pieces} == {"doc_a", "doc_b"}


async def test_flagged_chunks_never_selected(setup):
    content = texts("甲", 10)
    content[3] = "这一段命中了敏感词制毒，报销审批。"
    await setup.add_doc("doc_a", "甲.txt", content, flag={3})
    for seed in range(5):
        assert all("制毒" not in p.text for p in await setup.select(seed=seed))
    assert all("制毒" not in p.text for p in await setup.select("报销审批"))


async def test_only_selected_documents_and_own_user(setup):
    a = await setup.add_doc("doc_a", "甲.txt", texts("甲", 5, "报销"))
    await setup.add_doc("doc_b", "乙.txt", texts("乙", 5, "报销"))
    await setup.add_doc("doc_x", "别人.txt", texts("别人", 5, "报销"), user_id=2)
    for focus in ("", "报销"):
        pieces = await setup.select(focus, docs=[a])
        assert {p.document_id for p in pieces} == {"doc_a"}


# ---------- 有重点：向量检索 ----------


async def test_focus_retrieves_relevant_document(setup):
    await setup.add_doc("doc_pay", "报销制度.txt", texts("报销制度", 15, "报销审批流程"))
    await setup.add_doc("doc_att", "考勤制度.txt", texts("考勤制度", 15, "考勤打卡规则"))
    pieces = await setup.select("报销审批")
    assert pieces and {p.document_id for p in pieces} == {"doc_pay"}
    assert setup.embedder.calls == [["报销审批"]]
    assert len(pieces) <= 12


@pytest.mark.parametrize("where", ["embedding", "vector_store"])
async def test_retrieval_failure_falls_back_to_spread(setup, where, caplog):
    await setup.add_doc("doc_pay", "报销制度.txt", texts("报销制度", 15, "报销审批"))
    await setup.add_doc("doc_att", "考勤制度.txt", texts("考勤制度", 15, "考勤打卡"))
    if where == "embedding":
        setup.embedder.error = EmbeddingError("timeout")
    else:
        setup.vectors.fail_queries = RuntimeError("chroma down")
    pieces = await setup.select("报销审批")
    # 降级为均匀抽取：两份资料都有
    assert {p.document_id for p in pieces} == {"doc_pay", "doc_att"}
    assert "fall back to spread" in caplog.text


async def test_no_retrieval_hits_falls_back_to_spread(setup):
    doc = await setup.add_doc("doc_a", "甲.txt", texts("甲", 5))
    setup.vectors.vectors.clear()  # 向量丢了（比如索引被删），MySQL 里还有正文
    pieces = await setup.select("报销", docs=[doc])
    assert pieces and {p.document_id for p in pieces} == {"doc_a"}


# ---------- 独立的片段检索函数（出题服务与检索规划 Agent 共用）----------


async def _retrieve(setup, query: str, document_ids: list[str], *, user_id: int = 1, top_k: int = 6):
    return await retrieve_chunks(
        setup.db,
        user_id=user_id,
        document_ids=document_ids,
        query=query,
        embedder=setup.embedder,
        vector_store=setup.vectors,
        top_k=top_k,
    )


async def test_retrieve_chunks_orders_by_similarity_and_excludes_flagged(setup):
    pay = texts("报销制度", 4, "报销审批")
    pay[0] = "报销审批报销审批，命中敏感词制毒。"
    await setup.add_doc("doc_pay", "报销制度.txt", pay, flag={0})
    await setup.add_doc("doc_att", "考勤制度.txt", texts("考勤制度", 4, "考勤打卡"))
    rows = await _retrieve(setup, "报销审批", ["doc_pay", "doc_att"], top_k=3)
    assert setup.embedder.calls == [["报销审批"]]
    # 最相似的是 flagged 片段：占一个 top_k 名额但不返回
    assert [r["document_id"] for r in rows] == ["doc_pay"] * 2
    assert all("制毒" not in r["text"] for r in rows)
    assert set(rows[0]) >= {"id", "document_id", "seq", "page", "text"}


async def test_retrieve_chunks_limited_to_user_and_documents(setup):
    await setup.add_doc("doc_a", "甲.txt", texts("甲", 3, "报销"))
    await setup.add_doc("doc_b", "乙.txt", texts("乙", 3, "报销"))
    await setup.add_doc("doc_x", "别人.txt", texts("别人", 3, "报销"), user_id=2)
    rows = await _retrieve(setup, "报销", ["doc_a", "doc_x"])
    assert {r["document_id"] for r in rows} == {"doc_a"}
    assert await _retrieve(setup, "报销", ["doc_x"], user_id=1) == []


async def test_retrieve_chunks_raises_on_embedding_failure(setup):
    await setup.add_doc("doc_a", "甲.txt", texts("甲", 3))
    setup.embedder.error = EmbeddingError("timeout")
    with pytest.raises(EmbeddingError):
        await _retrieve(setup, "报销", ["doc_a"])
