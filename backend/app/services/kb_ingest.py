"""资料后台处理：解析 → 切块 → 敏感词标记 → 分批向量化 → 写片段与向量 → ready。

- 进程内 asyncio 任务，信号量限流（kb_process_concurrency）；关闭时统一取消。
- 最后一步在一个 MySQL 事务里：FOR UPDATE 确认资料还在且是 processing，写 kb_chunks 拿到 id，
  向量库 upsert，标为 ready，然后提交。upsert 失败则事务回滚；提交失败则清理向量。
- 资料在处理中被删除：放弃写入并清理向量，资料不会“复活”。
- 任何失败：尽力清理向量，资料标为 failed + 用户能看懂的原因。
- 无论成败，上传的临时文件都会删除。
"""

import asyncio
import logging
import time
from pathlib import Path

from app.core.config import Settings
from app.core.db import Database
from app.rag.embedding import Embedder, EmbeddingError
from app.rag.parsing import REASON_NO_TEXT, ParseError, chunk_segments, parse_document
from app.rag.vector_store import VectorMeta, VectorStore
from app.repositories import kb_repository as kbs
from app.repositories.kb_repository import NewChunk
from app.utils.content_filter import ContentFilter

logger = logging.getLogger(__name__)

REASON_EMBEDDING = "向量化服务暂时不可用，请稍后重新上传"
REASON_UNKNOWN = "处理失败，请稍后重新上传"


def failure_reason(exc: BaseException) -> str:
    if isinstance(exc, ParseError):
        return exc.reason
    if isinstance(exc, EmbeddingError):
        return REASON_EMBEDDING
    return REASON_UNKNOWN


class KbIngestor:
    def __init__(
        self,
        db: Database,
        *,
        settings: Settings,
        embedder: Embedder,
        vector_store: VectorStore,
        content_filter: ContentFilter,
    ):
        self._db = db
        self._settings = settings
        self._embedder = embedder
        self._vectors = vector_store
        self._filter = content_filter
        self._semaphore = asyncio.Semaphore(max(1, settings.kb_process_concurrency))
        self._tasks: set[asyncio.Task] = set()

    @property
    def pending(self) -> int:
        return len(self._tasks)

    def start(self, *, document_id: str, user_id: int, kb_id: str, path: Path, file_type: str) -> asyncio.Task:
        task = asyncio.create_task(
            self.process(document_id=document_id, user_id=user_id, kb_id=kb_id, path=path, file_type=file_type),
            name=f"kb-ingest-{document_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def process(self, *, document_id: str, user_id: int, kb_id: str, path: Path, file_type: str) -> str:
        """处理一份资料，返回最终结果：ready / failed / deleted。"""
        try:
            async with self._semaphore:
                return await self._process(document_id, user_id, kb_id, path, file_type)
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("remove upload %s failed: %s", path.name, type(exc).__name__)

    async def _process(self, document_id: str, user_id: int, kb_id: str, path: Path, file_type: str) -> str:
        s = self._settings
        start = time.perf_counter()
        try:
            parsed = await asyncio.to_thread(parse_document, path, file_type, max_chars=s.kb_max_chars)
            chunks = chunk_segments(parsed.segments, chunk_chars=s.kb_chunk_chars, overlap=s.kb_chunk_overlap)
            if not chunks:
                raise ParseError(REASON_NO_TEXT)
            # 命中敏感词的片段照常存（以后换词库可以重新判定），但不参与出题
            new_chunks = [
                NewChunk(seq=i, page=c.page, text=c.text, flagged=self._filter.find(c.text) is not None)
                for i, c in enumerate(chunks)
            ]
            embeddings = await self._embedder.embed([c.text for c in new_chunks])
            if len(embeddings) != len(new_chunks):
                raise EmbeddingError(f"expected {len(new_chunks)} embeddings, got {len(embeddings)}")

            async with self._db.transaction() as cur:
                doc = await kbs.lock_document(cur, document_id)
                if doc is None or doc["status"] != "processing":
                    abandoned = True
                else:
                    abandoned = False
                    ids = await kbs.insert_chunks(cur, document_id=document_id, user_id=user_id, chunks=new_chunks)
                    metas = [VectorMeta(user_id=user_id, kb_id=kb_id, document_id=document_id, page=c.page) for c in new_chunks]
                    await self._vectors.upsert(ids, embeddings, metas)
                    await kbs.mark_ready(
                        cur,
                        document_id,
                        page_count=parsed.page_count,
                        char_count=parsed.char_count,
                        chunk_count=len(new_chunks),
                    )
        # 进程关闭时的取消（CancelledError）不在这里处理：资料留在 processing，下次启动时标为“处理被中断”；
        # 也不清理向量——取消可能发生在提交过程中，残留的向量无害
        except Exception as exc:  # noqa: BLE001 —— 任何失败都落成 failed + 原因
            await self._drop_vectors(document_id)
            reason = failure_reason(exc)
            try:
                async with self._db.transaction() as cur:
                    await kbs.mark_failed(cur, document_id, reason)
            except Exception as db_exc:  # noqa: BLE001
                logger.error("mark document %s failed: %s", document_id, type(db_exc).__name__)
            logger.warning(
                "document %s failed after %.1fs: %s (%s)",
                document_id, time.perf_counter() - start, type(exc).__name__, reason,
            )
            return "failed"

        if abandoned:
            await self._drop_vectors(document_id)
            logger.info("document %s was deleted while processing, result discarded", document_id)
            return "deleted"
        logger.info(
            "document %s ready: %d chunks, %d chars, %s pages, %.1fs",
            document_id, len(new_chunks), parsed.char_count, parsed.page_count, time.perf_counter() - start,
        )
        return "ready"

    async def _drop_vectors(self, document_id: str) -> None:
        try:
            await self._vectors.delete_document(document_id)
        except Exception as exc:  # noqa: BLE001 —— 尽力清理；残留向量检索不到
            logger.warning("cleanup vectors of %s failed: %s", document_id, type(exc).__name__)

    async def aclose(self) -> None:
        """取消并等待所有未完成的处理任务。"""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
