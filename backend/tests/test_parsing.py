"""文档类型判断、提取、切块。测试文件都在测试内生成。"""

import zipfile
from pathlib import Path

import pytest

from app.rag.parsing import (
    REASON_BROKEN,
    REASON_NO_TEXT,
    REASON_SCANNED,
    ParseError,
    Segment,
    chunk_segments,
    detect_file_type,
    parse_document,
    reason_too_long,
)
from app.utils.text_cleaner import clean_text
from tests.kb_files import make_docx, make_pdf, page_text

MAX_CHARS = 300000


# ---------- 类型判断 ----------


def test_detect_types(tmp_path):
    assert detect_file_type("a.pdf", make_pdf(tmp_path / "a.pdf", [page_text(1)])) == "pdf"
    assert detect_file_type("B.DOCX", make_docx(tmp_path / "b.docx")) == "docx"
    (tmp_path / "c.txt").write_text("你好，世界", encoding="utf-8")
    assert detect_file_type("c.txt", tmp_path / "c.txt") == "txt"
    (tmp_path / "d.md").write_text("# 标题\n正文", encoding="utf-8")
    assert detect_file_type("d.md", tmp_path / "d.md") == "md"
    (tmp_path / "e.txt").write_bytes("国标编码的中文".encode("gb18030"))
    assert detect_file_type("e.txt", tmp_path / "e.txt") == "txt"


def test_detect_rejects_unsupported_and_disguised(tmp_path):
    txt = tmp_path / "fake.pdf"
    txt.write_text("我其实是文本文件", encoding="utf-8")
    assert detect_file_type("fake.pdf", txt) is None
    assert detect_file_type("slides.pptx", txt) is None
    assert detect_file_type("photo.png", txt) is None
    assert detect_file_type("noext", txt) is None
    # 扩展名是 docx 但不是 zip / 是 zip 但不是 Word
    assert detect_file_type("fake.docx", txt) is None
    zpath = tmp_path / "other.docx"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("ppt/presentation.xml", "<x/>")
    assert detect_file_type("other.docx", zpath) is None
    # 二进制内容伪装成 txt
    binary = tmp_path / "bin.txt"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    assert detect_file_type("bin.txt", binary) is None


# ---------- 提取 ----------


def test_multi_page_pdf_keeps_page_numbers(tmp_path):
    path = make_pdf(tmp_path / "a.pdf", [page_text(i) for i in range(1, 4)])
    doc = parse_document(path, "pdf", max_chars=MAX_CHARS)
    assert doc.page_count == 3
    assert [s.page for s in doc.segments] == [1, 2, 3]
    assert "Page 2" in doc.segments[1].text
    assert doc.char_count > 0


def test_pdf_without_text_is_scanned(tmp_path):
    path = make_pdf(tmp_path / "scan.pdf", ["", "", ""])
    with pytest.raises(ParseError) as info:
        parse_document(path, "pdf", max_chars=MAX_CHARS)
    assert info.value.reason == REASON_SCANNED


def test_pdf_with_too_little_text_per_page_is_scanned(tmp_path):
    # 10 页里只有 1 页有文字：平均每页不到 20 字
    path = make_pdf(tmp_path / "mostly_images.pdf", [page_text(1)] + [""] * 9)
    with pytest.raises(ParseError) as info:
        parse_document(path, "pdf", max_chars=MAX_CHARS)
    assert info.value.reason == REASON_SCANNED


def test_encrypted_pdf_is_broken(tmp_path):
    path = make_pdf(tmp_path / "locked.pdf", [page_text(1), page_text(2)], password="secret")
    with pytest.raises(ParseError) as info:
        parse_document(path, "pdf", max_chars=MAX_CHARS)
    assert info.value.reason == REASON_BROKEN


def test_truncated_pdf_is_broken(tmp_path):
    good = make_pdf(tmp_path / "good.pdf", [page_text(1), page_text(2)])
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(good.read_bytes()[:120])
    with pytest.raises(ParseError) as info:
        parse_document(bad, "pdf", max_chars=MAX_CHARS)
    assert info.value.reason == REASON_BROKEN


def test_docx_with_table(tmp_path):
    doc = parse_document(make_docx(tmp_path / "a.docx"), "docx", max_chars=MAX_CHARS)
    assert doc.page_count is None
    assert [s.page for s in doc.segments] == [None]
    text = doc.segments[0].text
    # 段落与表格按文档顺序
    assert text.index("报销制度") < text.index("部门经理") < text.index("表格之后")
    assert "5000 元以下 | 部门经理" in text


def test_broken_docx(tmp_path):
    path = tmp_path / "bad.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", "<not-really-xml")
    with pytest.raises(ParseError) as info:
        parse_document(path, "docx", max_chars=MAX_CHARS)
    assert info.value.reason == REASON_BROKEN


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gb18030"])
def test_txt_encodings(tmp_path, encoding):
    path = tmp_path / "a.txt"
    raw = "考勤制度：每天 9 点前打卡。\n迟到三次扣半天工资。"
    path.write_bytes(raw.encode(encoding))
    doc = parse_document(path, "txt", max_chars=MAX_CHARS)
    # 与用户输入一样经过 clean_text（NFKC 会把全角冒号变成半角）
    assert doc.segments == [Segment(page=None, text=clean_text(raw))]
    assert doc.segments[0].text.startswith("考勤制度")
    assert doc.page_count is None


def test_markdown_is_kept_as_is(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("# 标题\n\n- 要点一\n- 要点二", encoding="utf-8")
    assert parse_document(path, "md", max_chars=MAX_CHARS).segments[0].text == "# 标题\n\n- 要点一\n- 要点二"


def test_empty_text_file(tmp_path):
    path = tmp_path / "blank.txt"
    path.write_text("   \n\n  ", encoding="utf-8")
    with pytest.raises(ParseError) as info:
        parse_document(path, "txt", max_chars=MAX_CHARS)
    assert info.value.reason == REASON_NO_TEXT


def test_text_over_limit_is_too_long(tmp_path):
    path = tmp_path / "long.txt"
    path.write_text("字" * (MAX_CHARS + 1), encoding="utf-8")
    with pytest.raises(ParseError) as info:
        parse_document(path, "txt", max_chars=MAX_CHARS)
    assert info.value.reason == reason_too_long(MAX_CHARS)
    assert "30 万字" in info.value.reason


def test_text_at_limit_is_ok(tmp_path):
    path = tmp_path / "ok.txt"
    path.write_text("字" * MAX_CHARS, encoding="utf-8")
    assert parse_document(path, "txt", max_chars=MAX_CHARS).char_count == MAX_CHARS


# ---------- 切块 ----------

SENTENCE = "报销需要部门经理审批并且金额超过五千元还要财务总监签字。"  # 28 字，没有会被 NFKC 改写的全角符号


def test_chunks_respect_length_and_overlap():
    text = "\n\n".join(SENTENCE * 3 for _ in range(30))
    chunks = chunk_segments([Segment(page=None, text=text)], chunk_chars=500, overlap=80)
    assert len(chunks) > 3
    assert all(len(c.text) <= 500 for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:]):
        tail = prev.text[-80:].lstrip()
        assert nxt.text.startswith(tail)
    # 内容不丢：每一段都出现在某个块里
    assert "".join(c.text for c in chunks).count(SENTENCE) >= 90


def test_long_paragraph_is_split_by_sentence_then_hard():
    para = SENTENCE * 40  # 一整段 1080 字，没有空行
    chunks = chunk_segments([Segment(page=None, text=para)], chunk_chars=200, overlap=40)
    assert all(len(c.text) <= 200 for c in chunks)
    # 按句号切：除重叠部分外，块尾是完整句子
    assert all(c.text.endswith("。") for c in chunks)
    no_punct = "字" * 1000
    hard = chunk_segments([Segment(page=None, text=no_punct)], chunk_chars=200, overlap=40)
    assert all(len(c.text) <= 200 for c in hard)
    assert len(hard) >= 6


def test_short_text_is_one_chunk():
    chunks = chunk_segments([Segment(page=None, text="短短一段。")], chunk_chars=500, overlap=80)
    assert [c.text for c in chunks] == ["短短一段。"]


def test_pdf_chunks_do_not_cross_pages():
    segments = [Segment(page=1, text=SENTENCE * 30), Segment(page=2, text="第二页只有一句。")]
    chunks = chunk_segments(segments, chunk_chars=300, overlap=50)
    assert {c.page for c in chunks} == {1, 2}
    assert [c.text for c in chunks if c.page == 2] == ["第二页只有一句。"]
    assert all(SENTENCE[:5] not in c.text for c in chunks if c.page == 2)


def test_empty_segments_produce_no_chunks():
    assert chunk_segments([Segment(page=1, text="  \n\n ")], chunk_chars=500, overlap=80) == []


def test_parsed_pdf_chunks_carry_page(tmp_path):
    path = make_pdf(tmp_path / "a.pdf", [page_text(i) for i in range(1, 4)])
    doc = parse_document(path, "pdf", max_chars=MAX_CHARS)
    chunks = chunk_segments(doc.segments, chunk_chars=500, overlap=80)
    assert [c.page for c in chunks] == [1, 2, 3]
    assert "Page 3" in chunks[2].text
