"""文档类型判断、文字提取与切块。纯函数（同步），调用方用 asyncio.to_thread 放到线程池执行。

- 类型：扩展名必须是 .pdf / .docx / .txt / .md，且内容签名匹配。
- PDF：逐页提取，每页一个 Segment（页码从 1 开始）；切块不跨页，出处页码因此准确。
- DOCX：段落与表格按文档顺序提取；TXT / MD：整段解码（UTF-8 / GB18030）。没有页码。
- 失败抛 ParseError，reason 是给用户看的失败原因。
"""

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.utils.text_cleaner import clean_text, visible_length

EXTENSIONS = {".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".md": "md"}

REASON_SCANNED = "读不出文字，可能是扫描件或图片版 PDF，请上传文字版"
REASON_NO_TEXT = "文件里没有读到文字"
REASON_BROKEN = "文件打不开，可能已损坏或设置了密码"


def reason_too_long(max_chars: int) -> str:
    return f"内容太长（超过 {max_chars // 10000} 万字），请拆分后分别上传"


# 扫描件判断阈值：可见字符总数 / 平均每页字数
_PDF_MIN_TOTAL_CHARS = 50
_PDF_MIN_CHARS_PER_PAGE = 20


class ParseError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason


@dataclass(frozen=True)
class Segment:
    page: int | None
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    segments: list[Segment]
    page_count: int | None
    char_count: int


@dataclass(frozen=True)
class Chunk:
    page: int | None
    text: str


# ---------- 类型判断 ----------


def file_type_of(filename: str) -> str | None:
    return EXTENSIONS.get(Path(filename).suffix.lower())


def decode_text(raw: bytes) -> str | None:
    """按 UTF-8（含 BOM）或 GB18030 解码；含 NUL 或都解不开时返回 None（多半是二进制文件）。"""
    if b"\x00" in raw:
        return None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _is_docx(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            return "word/document.xml" in zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def detect_file_type(filename: str, path: Path) -> str | None:
    """扩展名与内容签名都匹配时返回 pdf / docx / txt / md，否则 None。"""
    file_type = file_type_of(filename)
    if file_type is None:
        return None
    if file_type == "pdf":
        with open(path, "rb") as f:
            return "pdf" if f.read(5) == b"%PDF-" else None
    if file_type == "docx":
        return "docx" if _is_docx(path) else None
    return file_type if decode_text(path.read_bytes()) is not None else None


# ---------- 提取 ----------


def _extract_pdf(path: Path) -> tuple[list[Segment], int]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ParseError(REASON_BROKEN, "encrypted pdf")
        segments = [Segment(page=i, text=clean_text(p.extract_text() or "")) for i, p in enumerate(reader.pages, 1)]
    except ParseError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, OSError, AttributeError, IndexError) as exc:
        raise ParseError(REASON_BROKEN, f"pdf parse failed: {type(exc).__name__}") from None
    page_count = len(segments)
    total = sum(visible_length(s.text) for s in segments)
    if page_count == 0 or total < _PDF_MIN_TOTAL_CHARS or total / page_count < _PDF_MIN_CHARS_PER_PAGE:
        raise ParseError(REASON_SCANNED, f"pdf has {total} visible chars on {page_count} pages")
    return segments, page_count


def _docx_table_text(table) -> str:
    rows = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            text = cell.text.strip()
            # 合并单元格会在每个被合并的位置重复出现
            if text and (not cells or cells[-1] != text):
                cells.append(text)
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _extract_docx(path: Path) -> list[Segment]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(str(path))
        parts: list[str] = []
        body = document.element.body
        for child in body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                parts.append(Paragraph(child, document).text)
            elif tag == "tbl":
                # 表格前后空一行，切块时单独成段
                parts.append("\n" + _docx_table_text(Table(child, document)) + "\n")
    except Exception as exc:  # noqa: BLE001 —— python-docx / lxml 的异常类型很多，一律视为文件损坏
        raise ParseError(REASON_BROKEN, f"docx parse failed: {type(exc).__name__}") from None
    return [Segment(page=None, text=clean_text("\n".join(parts)))]


def _extract_text_file(path: Path) -> list[Segment]:
    text = decode_text(path.read_bytes())
    if text is None:
        raise ParseError(REASON_BROKEN, "text decode failed")
    return [Segment(page=None, text=clean_text(text))]


def parse_document(path: Path, file_type: str, *, max_chars: int) -> ParsedDocument:
    if file_type == "pdf":
        segments, page_count = _extract_pdf(path)
    elif file_type == "docx":
        segments, page_count = _extract_docx(path), None
    elif file_type in ("txt", "md"):
        segments, page_count = _extract_text_file(path), None
    else:
        raise ParseError(REASON_BROKEN, f"unsupported type {file_type}")
    segments = [s for s in segments if s.text]
    char_count = sum(visible_length(s.text) for s in segments)
    if char_count == 0:
        raise ParseError(REASON_NO_TEXT)
    if char_count > max_chars:
        raise ParseError(reason_too_long(max_chars), f"{char_count} chars")
    return ParsedDocument(segments=segments, page_count=page_count, char_count=char_count)


# ---------- 切块 ----------

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# 句末标点（保留在句子末尾）
_SENTENCE = re.compile(r"[^。！？；!?;\n]+[。！？；!?;\n]*|[。！？；!?;\n]+")


def _split_long(text: str, limit: int) -> list[str]:
    """把超过 limit 的段落按句号等标点切开，单句仍超长时按长度硬切。"""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE.findall(text):
        while len(sentence) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:limit])
            sentence = sentence[limit:]
        if len(current) + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        pieces.append(current)
    return [p.strip() for p in pieces if p.strip()]


def _chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    overlap = max(0, min(overlap, chunk_chars // 2))
    # 每个单元最长 chunk_chars - overlap - 1，保证“上一块结尾 + 换行 + 单元”不超过 chunk_chars
    unit_limit = max(1, chunk_chars - overlap - 1)
    units: list[str] = []
    for para in _PARAGRAPH_BREAK.split(text):
        para = para.strip()
        if para:
            units += _split_long(para, unit_limit)

    chunks: list[str] = []
    current = ""
    fresh = False  # current 里是否有上一块没包含的新内容
    for unit in units:
        candidate = f"{current}\n{unit}" if current else unit
        if len(candidate) <= chunk_chars:
            current, fresh = candidate, True
            continue
        if fresh:
            chunks.append(current)
        tail = current[-overlap:].lstrip() if overlap and current else ""
        current = f"{tail}\n{unit}" if tail else unit
        fresh = True
    if fresh and current:
        chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]


def chunk_segments(segments: list[Segment], *, chunk_chars: int, overlap: int) -> list[Chunk]:
    """逐个 Segment（PDF 即逐页）切块，块不跨页。"""
    chunks: list[Chunk] = []
    for seg in segments:
        for text in _chunk_text(seg.text, chunk_chars, overlap):
            cleaned = clean_text(text)
            if cleaned:
                chunks.append(Chunk(page=seg.page, text=cleaned))
    return chunks
