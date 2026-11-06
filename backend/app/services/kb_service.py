"""知识库管理：建库、列表、详情、改名、删库，登记上传的资料，删资料。

文本与状态以 MySQL 为准；删除时先在 MySQL 事务里删，提交后再删向量（失败只记日志：
检索永远按 MySQL 里的资料列表过滤，残留的孤儿向量不会被用到）。
"""

import logging
from datetime import datetime
from pathlib import PurePath

from app.core.config import Settings
from app.core.db import Database
from app.core.exceptions import BizError, ErrorCode
from app.models.kb import KbDetail, KbDocument, KbList, KnowledgeBase
from app.rag.vector_store import VectorStore
from app.repositories import kb_repository as kbs
from app.utils.content_filter import ContentFilter
from app.utils.id_generator import new_document_id, new_kb_id
from app.utils.text_cleaner import clean_text
from app.utils.timeutil import iso_utc, utcnow

logger = logging.getLogger(__name__)

NAME_MAX_CHARS = 20
FILENAME_MAX_CHARS = 100
MSG_NAME_EMPTY = "知识库名称不能为空"
MSG_NAME_TOO_LONG = f"知识库名称最多 {NAME_MAX_CHARS} 个字"
MSG_NAME_NOT_ALLOWED = "这个名称不太合适，换一个试试"
MSG_KB_NOT_FOUND = "没找到这个知识库"
MSG_DOC_NOT_FOUND = "没找到这份资料"


def msg_kb_limit(limit: int) -> str:
    return f"最多建 {limit} 个知识库，删掉不用的再新建吧"


def msg_doc_limit(limit: int) -> str:
    return f"资料最多存 {limit} 份，删掉不用的再上传吧"


def to_document(row: dict) -> KbDocument:
    return KbDocument(
        document_id=row["document_id"],
        filename=row["filename"],
        file_type=row["file_type"],
        size_bytes=row["size_bytes"],
        status=row["status"],
        fail_reason=row["fail_reason"] if row["status"] == "failed" else None,
        page_count=row["page_count"],
        char_count=row["char_count"],
        created_at=iso_utc(row["created_at"]),
    )


def safe_filename(raw: str) -> str:
    """只保留文件名本身（去掉路径），清洗后截断；为空时给个默认名。"""
    name = " ".join(clean_text(PurePath(raw.replace("\\", "/")).name).split())
    if len(name) > FILENAME_MAX_CHARS:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: FILENAME_MAX_CHARS - len(ext) - 1] + dot + ext) if dot and len(ext) <= 8 else name[:FILENAME_MAX_CHARS]
    return name or "未命名资料"


class KbService:
    def __init__(
        self, db: Database, *, settings: Settings, content_filter: ContentFilter, vector_store: VectorStore
    ):
        self._db = db
        self._settings = settings
        self._filter = content_filter
        self._vectors = vector_store

    def _check_name(self, raw: str) -> str:
        name = " ".join(clean_text(raw).split())
        if not name:
            raise BizError(ErrorCode.INVALID_PARAMS, MSG_NAME_EMPTY)
        if len(name) > NAME_MAX_CHARS:
            raise BizError(ErrorCode.INVALID_PARAMS, MSG_NAME_TOO_LONG)
        if self._filter.find(name):
            raise BizError(ErrorCode.CONTENT_NOT_ALLOWED, MSG_NAME_NOT_ALLOWED)
        return name

    async def _kb(self, cur, user_id: int, kb_id: str, *, for_update: bool = False) -> KnowledgeBase:
        row = await kbs.get_kb(cur, user_id, kb_id, for_update=for_update)
        if row is None:
            raise BizError(ErrorCode.NOT_FOUND, MSG_KB_NOT_FOUND)
        docs = await kbs.list_documents(cur, user_id, kb_id)
        return KnowledgeBase(
            kb_id=row["kb_id"],
            name=row["name"],
            document_count=len(docs),
            ready_count=sum(d["status"] == "ready" for d in docs),
            created_at=iso_utc(row["created_at"]),
            updated_at=iso_utc(row["updated_at"]),
        )

    async def create(self, user_id: int, raw_name: str, *, now: datetime | None = None) -> KnowledgeBase:
        name = self._check_name(raw_name)
        kb_id = new_kb_id()
        async with self._db.transaction() as cur:
            if await kbs.count_kbs(cur, user_id) >= self._settings.kb_max_bases:
                raise BizError(ErrorCode.LIMIT_EXCEEDED, msg_kb_limit(self._settings.kb_max_bases))
            await kbs.insert_kb(cur, kb_id=kb_id, user_id=user_id, name=name, now=now or utcnow())
            kb = await self._kb(cur, user_id, kb_id)
        logger.info("user %s created knowledge base %s", user_id, kb_id)
        return kb

    async def list_all(self, user_id: int) -> KbList:
        async with self._db.transaction() as cur:
            rows = await kbs.list_kbs(cur, user_id)
            document_total = await kbs.count_documents(cur, user_id)
        items = [
            KnowledgeBase(
                kb_id=r["kb_id"],
                name=r["name"],
                document_count=int(r["document_count"]),
                ready_count=int(r["ready_count"]),
                created_at=iso_utc(r["created_at"]),
                updated_at=iso_utc(r["updated_at"]),
            )
            for r in rows
        ]
        return KbList(
            items=items,
            total=len(items),
            document_total=document_total,
            document_limit=self._settings.kb_max_documents,
        )

    async def detail(self, user_id: int, kb_id: str) -> KbDetail:
        async with self._db.transaction() as cur:
            kb = await self._kb(cur, user_id, kb_id)
            docs = await kbs.list_documents(cur, user_id, kb_id)
        return KbDetail(knowledge_base=kb, documents=[to_document(d) for d in docs])

    async def rename(self, user_id: int, kb_id: str, raw_name: str, *, now: datetime | None = None) -> KnowledgeBase:
        name = self._check_name(raw_name)
        async with self._db.transaction() as cur:
            if not await kbs.rename_kb(cur, user_id, kb_id, name, now or utcnow()):
                raise BizError(ErrorCode.NOT_FOUND, MSG_KB_NOT_FOUND)
            return await self._kb(cur, user_id, kb_id)

    async def delete(self, user_id: int, kb_id: str) -> None:
        async with self._db.transaction() as cur:
            document_ids = await kbs.delete_kb(cur, user_id, kb_id)
        if document_ids is None:
            raise BizError(ErrorCode.NOT_FOUND, MSG_KB_NOT_FOUND)
        logger.info("user %s deleted knowledge base %s (%d documents)", user_id, kb_id, len(document_ids))
        await self._drop_vectors(document_ids)

    async def delete_document(self, user_id: int, kb_id: str, document_id: str, *, now: datetime | None = None) -> None:
        async with self._db.transaction() as cur:
            if not await kbs.delete_document(cur, user_id, kb_id, document_id):
                raise BizError(ErrorCode.NOT_FOUND, MSG_DOC_NOT_FOUND)
            await kbs.touch_kb(cur, kb_id, now or utcnow())
        logger.info("user %s deleted document %s", user_id, document_id)
        await self._drop_vectors([document_id])

    async def _drop_vectors(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        try:
            await self._vectors.delete_documents(document_ids)
        except Exception as exc:  # noqa: BLE001 —— 孤儿向量无害（检索按 MySQL 资料列表过滤），不影响删除结果
            logger.warning("delete vectors of %d documents failed: %s", len(document_ids), type(exc).__name__)

    # ---------- 上传登记（接收文件、判断类型在路由里做） ----------

    async def check_upload_allowed(self, user_id: int, kb_id: str) -> None:
        """落盘之前先查：知识库归属、资料数上限。"""
        async with self._db.transaction() as cur:
            if await kbs.get_kb(cur, user_id, kb_id) is None:
                raise BizError(ErrorCode.NOT_FOUND, MSG_KB_NOT_FOUND)
            if await kbs.count_documents(cur, user_id) >= self._settings.kb_max_documents:
                raise BizError(ErrorCode.LIMIT_EXCEEDED, msg_doc_limit(self._settings.kb_max_documents))

    async def add_document(
        self,
        user_id: int,
        kb_id: str,
        *,
        filename: str,
        file_type: str,
        size_bytes: int,
        document_id: str | None = None,
        now: datetime | None = None,
    ) -> KbDocument:
        """登记一份处理中的资料，同时刷新知识库更新时间。"""
        now = now or utcnow()
        document_id = document_id or new_document_id()
        async with self._db.transaction() as cur:
            # 锁住知识库行：同一库的并发上传、删库在这里排队
            if await kbs.get_kb(cur, user_id, kb_id, for_update=True) is None:
                raise BizError(ErrorCode.NOT_FOUND, MSG_KB_NOT_FOUND)
            if await kbs.count_documents(cur, user_id) >= self._settings.kb_max_documents:
                raise BizError(ErrorCode.LIMIT_EXCEEDED, msg_doc_limit(self._settings.kb_max_documents))
            await kbs.insert_document(
                cur,
                document_id=document_id,
                kb_id=kb_id,
                user_id=user_id,
                filename=safe_filename(filename),
                file_type=file_type,
                size_bytes=size_bytes,
                now=now,
            )
            await kbs.touch_kb(cur, kb_id, now)
            row = await kbs.get_document(cur, user_id, kb_id, document_id)
        logger.info("user %s uploaded document %s (%s, %d bytes)", user_id, document_id, file_type, size_bytes)
        return to_document(row)
