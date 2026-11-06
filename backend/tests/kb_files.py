"""知识库测试辅助：在测试内生成资料文件（不放二进制夹具），以及假的 Embedder。"""

from pathlib import Path


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path: Path, pages: list[str], *, password: str | None = None) -> Path:
    """每页一段 ASCII 文字（Helvetica）；空字符串的页没有文字，模拟扫描件。"""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    for text in pages:
        page = writer.add_blank_page(612, 792)
        if not text:
            continue
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        lines = " ".join(f"({_pdf_escape(line)}) Tj T*" for line in text.split("\n"))
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td 14 TL {lines} ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if password:
        writer.encrypt(password)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def page_text(n: int) -> str:
    return f"Page {n} explains the reimbursement approval process.\nManagers approve claims within five days."


def make_docx(path: Path) -> Path:
    import docx

    d = docx.Document()
    d.add_paragraph("第一章 报销制度")
    d.add_paragraph("员工出差后 30 天内提交报销申请。")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "金额"
    table.cell(0, 1).text = "审批人"
    table.cell(1, 0).text = "5000 元以下"
    table.cell(1, 1).text = "部门经理"
    d.add_paragraph("表格之后的说明文字。")
    d.save(str(path))
    return path




def keyword_vector(text: str, keywords: tuple[str, ...]) -> list[float]:
    """每个关键词一维：出现次数。用来让“重点”检索在离线测试里有确定的相似度。"""
    v = [float(text.count(k)) for k in keywords]
    return v + [0.01]  # 避免零向量


class FakeEmbedder:
    """离线假 Embedder：按关键词出向量；可设置失败、记录调用、在返回前执行钩子。"""

    KEYWORDS = ("报销", "审批", "考勤", "打卡", "Page", "approval")

    def __init__(self):
        self.calls: list[list[str]] = []
        self.error: Exception | None = None
        self.before_return = None  # async () -> None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.error is not None:
            raise self.error
        if self.before_return is not None:
            await self.before_return()
        return [keyword_vector(t, self.KEYWORDS) for t in texts]
