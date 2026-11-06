"""检索规划 Agent 的知识库工具执行器：在某个用户的一组 ready 资料里做片段检索。

- 首页出题：documents=None，第一次用到时查该用户全部知识库里的 ready 资料（每请求组装，绑定 user_id）；
- 知识库出题：documents 是本次所选的 ready 资料。

检索本身复用 kb_materials.retrieve_chunks（限定 user_id 与资料范围、排除 flagged），所以只会查到当前用户自己的资料。
"""

from collections.abc import Sequence

from app.agent.retrieval_planner import KbChunk
from app.core.db import Database
from app.prompts.retrieval_agent_prompt import CatalogItem
from app.rag.embedding import Embedder
from app.rag.vector_store import VectorStore
from app.repositories import kb_repository as kbs
from app.services.kb_materials import retrieve_chunks


class KbRetriever:
    def __init__(
        self,
        db: Database,
        *,
        user_id: int,
        embedder: Embedder,
        vector_store: VectorStore,
        top_k: int,
        documents: Sequence[dict] | None = None,
    ):
        self._db = db
        self._user_id = user_id
        self._embedder = embedder
        self._vectors = vector_store
        self._top_k = top_k
        self._documents = list(documents) if documents is not None else None

    async def documents(self) -> list[dict]:
        """可检索的资料（document_id、filename，首页还有 kb_name）；首页第一次调用时查库。"""
        if self._documents is None:
            async with self._db.transaction() as cur:
                self._documents = await kbs.list_ready_documents(cur, self._user_id)
        return self._documents

    async def catalog(self) -> list[CatalogItem]:
        return [CatalogItem(kb_name=d.get("kb_name", ""), filename=d["filename"]) for d in await self.documents()]

    async def search(self, query: str) -> list[KbChunk]:
        documents = await self.documents()
        names = {d["document_id"]: d["filename"] for d in documents}
        rows = await retrieve_chunks(
            self._db,
            user_id=self._user_id,
            document_ids=list(names),
            query=query,
            embedder=self._embedder,
            vector_store=self._vectors,
            top_k=self._top_k,
        )
        return [
            KbChunk(
                id=int(r["id"]),
                document_id=r["document_id"],
                document_name=names.get(r["document_id"], ""),
                seq=int(r["seq"]),
                page=r["page"],
                text=r["text"],
            )
            for r in rows
        ]
