"""同一组用例跑 Chroma（tmp_path，真实读写）和内存实现。"""

import pytest

from app.rag.vector_store import ChromaVectorStore, InMemoryVectorStore, VectorMeta, collection_name

DIM = 1024


def unit(axis: int, tilt: float = 0.0) -> list[float]:
    """第 axis 维为 1 的向量；tilt 往第 0 维偏一点，用来造“相似但不完全相同”。"""
    v = [0.0] * DIM
    v[axis] = 1.0
    v[0] += tilt
    return v


@pytest.fixture(params=["chroma", "memory"])
def store(request, tmp_path):
    if request.param == "memory":
        yield InMemoryVectorStore()
        return
    s = ChromaVectorStore(str(tmp_path / "chroma"), model="BAAI/bge-m3")
    yield s
    s.close()


async def seed(store):
    await store.upsert(
        [1, 2, 3, 4],
        [unit(1), unit(1, 0.5), unit(2), unit(1)],
        [
            VectorMeta(user_id=1, kb_id="kb_a", document_id="doc_a", page=1),
            VectorMeta(user_id=1, kb_id="kb_a", document_id="doc_b"),
            VectorMeta(user_id=1, kb_id="kb_a", document_id="doc_a", page=2),
            VectorMeta(user_id=2, kb_id="kb_x", document_id="doc_x", page=1),
        ],
    )


async def test_query_orders_by_similarity_and_filters_user(store):
    await seed(store)
    got = await store.query(unit(1), user_id=1, document_ids=["doc_a", "doc_b"], top_k=10)
    assert got == [1, 2, 3]
    # 别的用户的同样向量查不到
    assert 4 not in got


async def test_query_only_returns_selected_documents(store):
    await seed(store)
    assert await store.query(unit(1), user_id=1, document_ids=["doc_b"], top_k=10) == [2]
    assert await store.query(unit(1), user_id=1, document_ids=["doc_x"], top_k=10) == []
    assert await store.query(unit(1), user_id=1, document_ids=[], top_k=10) == []


async def test_query_respects_top_k(store):
    await seed(store)
    assert await store.query(unit(1), user_id=1, document_ids=["doc_a", "doc_b"], top_k=2) == [1, 2]


async def test_delete_document_removes_its_vectors(store):
    await seed(store)
    await store.delete_document("doc_a")
    assert await store.query(unit(1), user_id=1, document_ids=["doc_a", "doc_b"], top_k=10) == [2]
    await store.delete_documents(["doc_b", "doc_x"])
    assert await store.query(unit(1), user_id=1, document_ids=["doc_a", "doc_b"], top_k=10) == []
    assert await store.query(unit(1), user_id=2, document_ids=["doc_x"], top_k=10) == []
    assert store.count() == 0


async def test_upsert_overwrites_same_id(store):
    await seed(store)
    await store.upsert([1], [unit(3)], [VectorMeta(user_id=1, kb_id="kb_a", document_id="doc_a", page=1)])
    assert (await store.query(unit(3), user_id=1, document_ids=["doc_a"], top_k=1)) == [1]
    assert store.count() == 4


async def test_empty_store_query(store):
    assert await store.query(unit(1), user_id=1, document_ids=["doc_a"], top_k=5) == []


def test_chroma_persists_across_clients(tmp_path):
    import asyncio

    path = str(tmp_path / "chroma")
    s = ChromaVectorStore(path, model="BAAI/bge-m3")
    asyncio.run(s.upsert([7], [unit(5)], [VectorMeta(user_id=1, kb_id="kb_a", document_id="doc_a")]))
    s.close()
    s2 = ChromaVectorStore(path, model="BAAI/bge-m3")
    try:
        assert asyncio.run(s2.query(unit(5), user_id=1, document_ids=["doc_a"], top_k=3)) == [7]
    finally:
        s2.close()


def test_collection_name_includes_model():
    assert collection_name("BAAI/bge-m3") == "kb_chunks__bge_m3"
    assert collection_name("Qwen/Qwen3-Embedding-8B") == "kb_chunks__qwen3_embedding_8b"
