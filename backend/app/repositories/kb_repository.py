"""knowledge_bases / kb_documents / kb_chunks 的 SQL。函数都接收事务游标（DictCursor）。

用户隔离：凡是按业务 id 取知识库 / 资料的查询都同时带 user_id，查不到即视为不存在。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from aiomysql import DictCursor

MSG_INTERRUPTED = "处理被中断，请重新上传"

_DOC_COLUMNS = (
    "document_id, kb_id, user_id, filename, file_type, size_bytes, status, fail_reason, page_count, "
    "char_count, chunk_count, created_at"
)

# 一条 INSERT 最多写多少块（executemany 会改写成多行 VALUES）
_CHUNK_INSERT_BATCH = 200


@dataclass(frozen=True)
class NewChunk:
    seq: int
    page: int | None
    text: str
    flagged: bool = False


def _placeholders(n: int) -> str:
    return ", ".join(["%s"] * n)


# ---------- 知识库 ----------


async def insert_kb(cur: DictCursor, *, kb_id: str, user_id: int, name: str, now: datetime) -> None:
    await cur.execute(
        "INSERT INTO knowledge_bases (kb_id, user_id, name, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
        (kb_id, user_id, name, now, now),
    )


async def count_kbs(cur: DictCursor, user_id: int) -> int:
    await cur.execute("SELECT COUNT(*) AS n FROM knowledge_bases WHERE user_id = %s", (user_id,))
    return int((await cur.fetchone())["n"])


async def list_kbs(cur: DictCursor, user_id: int) -> list[dict]:
    """该用户全部知识库（带资料总数、可出题资料数），按更新时间从新到旧。"""
    await cur.execute(
        "SELECT k.kb_id, k.name, k.created_at, k.updated_at, "
        "COUNT(d.id) AS document_count, COALESCE(SUM(d.status = 'ready'), 0) AS ready_count "
        "FROM knowledge_bases k LEFT JOIN kb_documents d ON d.kb_id = k.kb_id AND d.user_id = k.user_id "
        "WHERE k.user_id = %s GROUP BY k.id ORDER BY k.updated_at DESC, k.id DESC",
        (user_id,),
    )
    return list(await cur.fetchall())


async def get_kb(cur: DictCursor, user_id: int, kb_id: str, *, for_update: bool = False) -> dict | None:
    await cur.execute(
        "SELECT kb_id, user_id, name, created_at, updated_at FROM knowledge_bases "
        "WHERE kb_id = %s AND user_id = %s" + (" FOR UPDATE" if for_update else ""),
        (kb_id, user_id),
    )
    return await cur.fetchone()


async def rename_kb(cur: DictCursor, user_id: int, kb_id: str, name: str, now: datetime) -> bool:
    await cur.execute(
        "UPDATE knowledge_bases SET name = %s, updated_at = %s WHERE kb_id = %s AND user_id = %s",
        (name, now, kb_id, user_id),
    )
    return cur.rowcount == 1


async def touch_kb(cur: DictCursor, kb_id: str, now: datetime) -> None:
    await cur.execute("UPDATE knowledge_bases SET updated_at = %s WHERE kb_id = %s", (now, kb_id))


async def delete_kb(cur: DictCursor, user_id: int, kb_id: str) -> list[str] | None:
    """删除知识库及其全部资料和片段，返回被删资料的 document_id；知识库不存在时返回 None。"""
    if await get_kb(cur, user_id, kb_id, for_update=True) is None:
        return None
    await cur.execute(
        "SELECT document_id FROM kb_documents WHERE kb_id = %s AND user_id = %s FOR UPDATE", (kb_id, user_id)
    )
    document_ids = [r["document_id"] for r in await cur.fetchall()]
    if document_ids:
        await cur.execute(
            f"DELETE FROM kb_chunks WHERE user_id = %s AND document_id IN ({_placeholders(len(document_ids))})",
            (user_id, *document_ids),
        )
        await cur.execute("DELETE FROM kb_documents WHERE kb_id = %s AND user_id = %s", (kb_id, user_id))
    await cur.execute("DELETE FROM knowledge_bases WHERE kb_id = %s AND user_id = %s", (kb_id, user_id))
    return document_ids


# ---------- 资料 ----------


async def count_documents(cur: DictCursor, user_id: int) -> int:
    """该用户所有知识库合计的资料数（含处理中和失败的）。"""
    await cur.execute("SELECT COUNT(*) AS n FROM kb_documents WHERE user_id = %s", (user_id,))
    return int((await cur.fetchone())["n"])


async def insert_document(
    cur: DictCursor,
    *,
    document_id: str,
    kb_id: str,
    user_id: int,
    filename: str,
    file_type: str,
    size_bytes: int,
    now: datetime,
) -> None:
    await cur.execute(
        "INSERT INTO kb_documents (document_id, kb_id, user_id, filename, file_type, size_bytes, status, "
        "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, 'processing', %s, %s)",
        (document_id, kb_id, user_id, filename, file_type, size_bytes, now, now),
    )


async def list_documents(cur: DictCursor, user_id: int, kb_id: str) -> list[dict]:
    """知识库里的全部资料，按上传时间从新到旧。"""
    await cur.execute(
        f"SELECT {_DOC_COLUMNS} FROM kb_documents WHERE kb_id = %s AND user_id = %s "
        "ORDER BY created_at DESC, id DESC",
        (kb_id, user_id),
    )
    return list(await cur.fetchall())


async def list_ready_documents(cur: DictCursor, user_id: int) -> list[dict]:
    """该用户所有知识库里可出题（ready）的资料，带知识库名；按上传时间从旧到新。"""
    await cur.execute(
        "SELECT d.document_id, d.filename, k.name AS kb_name FROM kb_documents d "
        "JOIN knowledge_bases k ON k.kb_id = d.kb_id AND k.user_id = d.user_id "
        "WHERE d.user_id = %s AND d.status = 'ready' ORDER BY d.created_at, d.id",
        (user_id,),
    )
    return list(await cur.fetchall())


async def get_document(cur: DictCursor, user_id: int, kb_id: str, document_id: str) -> dict | None:
    await cur.execute(
        f"SELECT {_DOC_COLUMNS} FROM kb_documents WHERE document_id = %s AND kb_id = %s AND user_id = %s",
        (document_id, kb_id, user_id),
    )
    return await cur.fetchone()


async def lock_document(cur: DictCursor, document_id: str) -> dict | None:
    """后台处理最后一步用：锁住资料行，确认它还在、还是 processing。"""
    await cur.execute(f"SELECT {_DOC_COLUMNS} FROM kb_documents WHERE document_id = %s FOR UPDATE", (document_id,))
    return await cur.fetchone()


async def delete_document(cur: DictCursor, user_id: int, kb_id: str, document_id: str) -> bool:
    """删除资料及其片段。资料不存在（或不属于该用户 / 该库）时返回 False。"""
    await cur.execute(
        "SELECT id FROM kb_documents WHERE document_id = %s AND kb_id = %s AND user_id = %s FOR UPDATE",
        (document_id, kb_id, user_id),
    )
    if await cur.fetchone() is None:
        return False
    await cur.execute("DELETE FROM kb_chunks WHERE document_id = %s AND user_id = %s", (document_id, user_id))
    await cur.execute("DELETE FROM kb_documents WHERE document_id = %s AND user_id = %s", (document_id, user_id))
    return True


async def mark_ready(
    cur: DictCursor, document_id: str, *, page_count: int | None, char_count: int, chunk_count: int
) -> None:
    await cur.execute(
        "UPDATE kb_documents SET status = 'ready', fail_reason = NULL, page_count = %s, char_count = %s, "
        "chunk_count = %s WHERE document_id = %s",
        (page_count, char_count, chunk_count, document_id),
    )


async def mark_failed(cur: DictCursor, document_id: str, reason: str) -> bool:
    """只把仍在处理中的资料标为失败；资料已删除时什么都不做。"""
    await cur.execute(
        "UPDATE kb_documents SET status = 'failed', fail_reason = %s WHERE document_id = %s AND status = 'processing'",
        (reason, document_id),
    )
    return cur.rowcount == 1


async def fail_interrupted(cur: DictCursor) -> int:
    """启动恢复：上次进程退出时还在处理中的资料一律标为失败。返回改动的行数。"""
    await cur.execute(
        "UPDATE kb_documents SET status = 'failed', fail_reason = %s WHERE status = 'processing'", (MSG_INTERRUPTED,)
    )
    return cur.rowcount


# ---------- 片段 ----------


async def insert_chunks(cur: DictCursor, *, document_id: str, user_id: int, chunks: Sequence[NewChunk]) -> list[int]:
    """批量写入片段，返回与 chunks 一一对应的自增 id（也是 Chroma 中的向量 id）。"""
    rows = [(document_id, user_id, c.seq, c.page, c.text, int(c.flagged)) for c in chunks]
    for i in range(0, len(rows), _CHUNK_INSERT_BATCH):
        await cur.executemany(
            "INSERT INTO kb_chunks (document_id, user_id, seq, page, text, flagged) VALUES (%s, %s, %s, %s, %s, %s)",
            rows[i : i + _CHUNK_INSERT_BATCH],
        )
    # 不依赖批量插入的自增连续性：按 seq 回查 id
    await cur.execute("SELECT id, seq FROM kb_chunks WHERE document_id = %s", (document_id,))
    by_seq = {r["seq"]: int(r["id"]) for r in await cur.fetchall()}
    return [by_seq[c.seq] for c in chunks]


async def list_chunk_positions(cur: DictCursor, user_id: int, document_ids: Sequence[str]) -> dict[str, list[int]]:
    """各资料可出题片段（排除 flagged）的 seq 列表，升序。"""
    if not document_ids:
        return {}
    await cur.execute(
        "SELECT document_id, seq FROM kb_chunks WHERE user_id = %s AND flagged = 0 "
        f"AND document_id IN ({_placeholders(len(document_ids))}) ORDER BY document_id, seq",
        (user_id, *document_ids),
    )
    positions: dict[str, list[int]] = {d: [] for d in document_ids}
    for r in await cur.fetchall():
        positions[r["document_id"]].append(int(r["seq"]))
    return positions


async def get_chunks_by_seq(cur: DictCursor, user_id: int, picks: dict[str, Sequence[int]]) -> list[dict]:
    """按 {document_id: [seq, ...]} 取片段正文（排除 flagged），按资料、seq 排序。"""
    conds, args = [], [user_id]
    for document_id, seqs in picks.items():
        if seqs:
            conds.append(f"(document_id = %s AND seq IN ({_placeholders(len(seqs))}))")
            args += [document_id, *seqs]
    if not conds:
        return []
    await cur.execute(
        "SELECT id, document_id, seq, page, text FROM kb_chunks WHERE user_id = %s AND flagged = 0 "
        f"AND ({' OR '.join(conds)}) ORDER BY document_id, seq",
        args,
    )
    return list(await cur.fetchall())


async def get_chunks_by_ids(
    cur: DictCursor, user_id: int, chunk_ids: Sequence[int], document_ids: Sequence[str]
) -> list[dict]:
    """按 id 取片段（向量检索结果），同时限定用户与资料范围、排除 flagged；返回顺序与 chunk_ids 一致。"""
    if not chunk_ids or not document_ids:
        return []
    await cur.execute(
        "SELECT id, document_id, seq, page, text FROM kb_chunks WHERE user_id = %s AND flagged = 0 "
        f"AND id IN ({_placeholders(len(chunk_ids))}) AND document_id IN ({_placeholders(len(document_ids))})",
        (user_id, *chunk_ids, *document_ids),
    )
    by_id = {int(r["id"]): r for r in await cur.fetchall()}
    return [by_id[i] for i in chunk_ids if i in by_id]
