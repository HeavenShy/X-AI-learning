"""向量库封装。正文以 MySQL kb_chunks 为准，这里只存向量和过滤用的 metadata（可从 MySQL 重建）。

向量 id 即 kb_chunks.id。检索时同时按 user_id 和 document_id ∈ {调用方从 MySQL 查出的资料} 过滤：
即使删除时留下孤儿向量，也永远不会被检索到。
"""

import asyncio
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VectorMeta:
    user_id: int
    kb_id: str
    document_id: str
    page: int | None = None


class VectorStore(Protocol):
    async def upsert(self, ids: Sequence[int], embeddings: Sequence[Sequence[float]], metadatas: Sequence[VectorMeta]) -> None: ...

    async def query(
        self, embedding: Sequence[float], *, user_id: int, document_ids: Sequence[str], top_k: int
    ) -> list[int]:
        """返回最相似的片段 id，按相似度从高到低。"""
        ...

    async def delete_document(self, document_id: str) -> None: ...

    async def delete_documents(self, document_ids: Sequence[str]) -> None: ...


def collection_name(model: str) -> str:
    """集合名带模型标识：换 Embedding 模型就换一个集合，旧向量不会混用。"""
    slug = re.sub(r"[^a-z0-9]+", "_", model.split("/")[-1].lower()).strip("_")
    return f"kb_chunks__{slug or 'default'}"


def _metadata(meta: VectorMeta) -> dict:
    # Chroma 的 metadata 不存 None：没有页码时不写 page
    data = {"user_id": meta.user_id, "kb_id": meta.kb_id, "document_id": meta.document_id}
    if meta.page is not None:
        data["page"] = meta.page
    return data


class ChromaVectorStore:
    """嵌入式 Chroma（PersistentClient）。Python API 是同步的：调用都放线程池，写操作再用一把锁串行化。"""

    def __init__(self, path: str, *, model: str):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
        # 不挂默认 embedding function（否则会下载本地 ONNX 模型），向量全部由调用方传入
        self._collection = self._client.get_or_create_collection(
            collection_name(model), metadata={"hnsw:space": "cosine"}, embedding_function=None
        )
        self._write_lock = asyncio.Lock()

    async def upsert(
        self, ids: Sequence[int], embeddings: Sequence[Sequence[float]], metadatas: Sequence[VectorMeta]
    ) -> None:
        if not ids:
            return
        async with self._write_lock:
            await asyncio.to_thread(
                self._collection.upsert,
                ids=[str(i) for i in ids],
                embeddings=[list(e) for e in embeddings],
                metadatas=[_metadata(m) for m in metadatas],
            )

    async def query(
        self, embedding: Sequence[float], *, user_id: int, document_ids: Sequence[str], top_k: int
    ) -> list[int]:
        if not document_ids or top_k <= 0:
            return []
        result = await asyncio.to_thread(
            self._collection.query,
            query_embeddings=[list(embedding)],
            n_results=top_k,
            where={"$and": [{"user_id": user_id}, {"document_id": {"$in": list(document_ids)}}]},
            include=["distances"],
        )
        return [int(i) for i in (result.get("ids") or [[]])[0]]

    async def delete_document(self, document_id: str) -> None:
        await self.delete_documents([document_id])

    async def delete_documents(self, document_ids: Sequence[str]) -> None:
        if not document_ids:
            return
        async with self._write_lock:
            await asyncio.to_thread(self._collection.delete, where={"document_id": {"$in": list(document_ids)}})

    def count(self) -> int:
        return self._collection.count()

    def close(self) -> None:
        self._client.close()


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class InMemoryVectorStore:
    """测试用：纯 Python 余弦相似度，行为与 ChromaVectorStore 一致。"""

    def __init__(self):
        self.vectors: dict[int, tuple[list[float], VectorMeta]] = {}
        self.fail_next_upsert: Exception | None = None
        self.fail_queries: Exception | None = None

    async def upsert(
        self, ids: Sequence[int], embeddings: Sequence[Sequence[float]], metadatas: Sequence[VectorMeta]
    ) -> None:
        if self.fail_next_upsert is not None:
            exc, self.fail_next_upsert = self.fail_next_upsert, None
            raise exc
        for i, e, m in zip(ids, embeddings, metadatas, strict=True):
            self.vectors[int(i)] = (list(e), m)

    async def query(
        self, embedding: Sequence[float], *, user_id: int, document_ids: Sequence[str], top_k: int
    ) -> list[int]:
        if self.fail_queries is not None:
            raise self.fail_queries
        allowed = set(document_ids)
        scored = [
            (_cosine(embedding, e), i)
            for i, (e, m) in self.vectors.items()
            if m.user_id == user_id and m.document_id in allowed
        ]
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [i for _, i in scored[: max(0, top_k)]]

    async def delete_document(self, document_id: str) -> None:
        await self.delete_documents([document_id])

    async def delete_documents(self, document_ids: Sequence[str]) -> None:
        drop = set(document_ids)
        self.vectors = {i: v for i, v in self.vectors.items() if v[1].document_id not in drop}

    def document_ids(self) -> set[str]:
        return {m.document_id for _, m in self.vectors.values()}

    def count(self) -> int:
        return len(self.vectors)
