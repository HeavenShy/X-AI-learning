"""知识库接口（yhyd_test + 假 Embedding + 内存向量库）。"""

import re

from fastapi.testclient import TestClient

from app.rag.vector_store import InMemoryVectorStore
from app.services.web_search import SearchSnippet
from tests.conftest import build_app, kb_settings
from tests.kb_files import FakeEmbedder, make_docx, make_pdf, page_text
from tests.llm_mock import MockDeepSeek, text_response, tool_calls_response

MB = 1024 * 1024


def pdf_bytes(tmp_path, pages: int = 3, name: str = "a.pdf") -> bytes:
    return make_pdf(tmp_path / name, [page_text(i) for i in range(1, pages + 1)]).read_bytes()


# ---------- 功能开关与登录 ----------


def test_knowledge_base_disabled_without_key(api):
    token, _ = api.login("u1")
    for resp in (
        api.get("/knowledge-bases", token),
        api.post("/knowledge-bases", {"name": "甲"}, token),
        api.get("/knowledge-bases/kb_x", token),
        api.upload("/knowledge-bases/kb_x/documents", "a.txt", "你好世界".encode(), token),
    ):
        assert resp.status_code == 503
        assert resp.json()["code"] == 5000
    # 文本出题照常
    body = api.post("/quiz/generate", {"user_input": "什么是 RAG 检索增强生成"}, token).json()
    assert body["code"] == 0


def test_knowledge_base_disabled_without_db(tmp_path):
    from app.main import create_app

    settings = kb_settings(tmp_path, mysql_database="")
    app = create_app(settings)
    with TestClient(app) as client:
        from app.core.auth import create_token

        token = create_token(1, "o-1", settings)
        resp = client.get("/api/v1/knowledge-bases", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 503 and resp.json()["code"] == 5000


def test_all_endpoints_require_login(kb_api):
    for resp in (
        kb_api.get("/knowledge-bases"),
        kb_api.post("/knowledge-bases", {"name": "甲"}),
        kb_api.get("/knowledge-bases/kb_x"),
        kb_api.put("/knowledge-bases/kb_x", {"name": "乙"}),
        kb_api.delete("/knowledge-bases/kb_x"),
        kb_api.upload("/knowledge-bases/kb_x/documents", "a.txt", "你好世界".encode()),
        kb_api.delete("/knowledge-bases/kb_x/documents/doc_x"),
    ):
        assert resp.status_code == 401
        assert resp.json()["code"] == 4010


# ---------- 管理接口 ----------


def test_create_list_detail_rename_delete(kb_api):
    token, _ = kb_api.login("u1")
    created = kb_api.post("/knowledge-bases", {"name": "公司新人考核"}, token).json()
    assert created["code"] == 0
    kb = created["data"]
    assert kb["name"] == "公司新人考核" and kb["document_count"] == 0
    assert kb["created_at"].endswith("Z") and kb["updated_at"].endswith("Z")

    listing = kb_api.get("/knowledge-bases", token).json()["data"]
    assert [k["kb_id"] for k in listing["items"]] == [kb["kb_id"]]
    assert (listing["document_total"], listing["document_limit"]) == (0, 50)

    detail = kb_api.get(f"/knowledge-bases/{kb['kb_id']}", token).json()["data"]
    assert detail["knowledge_base"]["name"] == "公司新人考核" and detail["documents"] == []

    renamed = kb_api.put(f"/knowledge-bases/{kb['kb_id']}", {"name": "PMP 备考"}, token).json()
    assert renamed["code"] == 0 and renamed["data"]["name"] == "PMP 备考"
    assert kb_api.get("/knowledge-bases", token).json()["data"]["items"][0]["name"] == "PMP 备考"

    assert kb_api.delete(f"/knowledge-bases/{kb['kb_id']}", token).json() == {"code": 0, "message": "ok", "data": None}
    assert kb_api.get("/knowledge-bases", token).json()["data"]["items"] == []
    assert kb_api.get(f"/knowledge-bases/{kb['kb_id']}", token).json()["code"] == 4040


def test_create_validation(kb_api):
    token, _ = kb_api.login("u1")
    assert kb_api.post("/knowledge-bases", {"name": "  "}, token).json()["code"] == 4000
    assert kb_api.post("/knowledge-bases", {"name": "字" * 21}, token).json()["code"] == 4000
    assert kb_api.post("/knowledge-bases", {"name": "傻瓜蛋的库"}, token).json()["code"] == 4003
    for i in range(10):
        assert kb_api.post("/knowledge-bases", {"name": f"库{i}"}, token).json()["code"] == 0
    over = kb_api.post("/knowledge-bases", {"name": "第十一个"}, token).json()
    assert over["code"] == 4022 and "10" in over["message"]


def test_list_counts_documents(kb_api, tmp_path):
    token, _ = kb_api.login("u1")
    a = kb_api.create_kb(token, "甲")
    b = kb_api.create_kb(token, "乙")
    for i in range(3):
        kb_api.upload(f"/knowledge-bases/{a}/documents", f"{i}.txt", f"考勤打卡规则第 {i} 条".encode(), token)
    kb_api.upload(f"/knowledge-bases/{b}/documents", "x.txt", "报销审批规则".encode(), token)
    kb_api.wait_documents(token, a)
    kb_api.wait_documents(token, b)
    listing = kb_api.get("/knowledge-bases", token).json()["data"]
    counts = {k["name"]: (k["document_count"], k["ready_count"]) for k in listing["items"]}
    assert counts == {"甲": (3, 3), "乙": (1, 1)}
    assert listing["document_total"] == 4
    # 删库：资料总数减 3
    kb_api.delete(f"/knowledge-bases/{a}", token)
    assert kb_api.get("/knowledge-bases", token).json()["data"]["document_total"] == 1


# ---------- 上传 ----------


def test_upload_returns_processing_then_becomes_ready(kb_api, tmp_path):
    token, _ = kb_api.login("u1")
    kb_id = kb_api.create_kb(token)
    resp = kb_api.upload(f"/knowledge-bases/{kb_id}/documents", "员工手册.pdf", pdf_bytes(tmp_path, 9), token)
    body = resp.json()
    assert body["code"] == 0, body
    doc = body["data"]
    assert doc["status"] == "processing"
    assert (doc["filename"], doc["file_type"]) == ("员工手册.pdf", "pdf")
    assert doc["size_bytes"] > 0 and doc["fail_reason"] is None
    docs = kb_api.wait_documents(token, kb_id)
    assert [(d["document_id"], d["status"], d["page_count"]) for d in docs] == [(doc["document_id"], "ready", 9)]
    assert docs[0]["char_count"] > 0
    assert kb_api.vectors.document_ids() == {doc["document_id"]}
    # 处理结束后上传文件被删除
    assert list(kb_api.upload_dir.iterdir()) == []


def test_upload_docx_txt_md(kb_api, tmp_path):
    token, _ = kb_api.login("u1")
    kb_id = kb_api.create_kb(token)
    docx_bytes = make_docx(tmp_path / "a.docx").read_bytes()
    for name, content in (
        ("制度.docx", docx_bytes),
        ("笔记.txt", "考勤：每天九点打卡。".encode("gb18030")),
        ("README.md", "# 标题\n\n报销审批流程".encode()),
    ):
        assert kb_api.upload(f"/knowledge-bases/{kb_id}/documents", name, content, token).json()["code"] == 0
    docs = kb_api.wait_documents(token, kb_id)
    assert sorted((d["file_type"], d["status"], d["page_count"]) for d in docs) == [
        ("docx", "ready", None), ("md", "ready", None), ("txt", "ready", None),
    ]


def test_upload_scanned_pdf_fails_with_reason(kb_api, tmp_path):
    token, _ = kb_api.login("u1")
    kb_id = kb_api.create_kb(token)
    scan = make_pdf(tmp_path / "scan.pdf", ["", ""]).read_bytes()
    assert kb_api.upload(f"/knowledge-bases/{kb_id}/documents", "扫描件.pdf", scan, token).json()["code"] == 0
    docs = kb_api.wait_documents(token, kb_id)
    assert docs[0]["status"] == "failed"
    assert "扫描件" in docs[0]["fail_reason"]


def test_upload_rejects_size(kb_api):
    token, _ = kb_api.login("u1")
    kb_id = kb_api.create_kb(token)
    big = kb_api.upload(f"/knowledge-bases/{kb_id}/documents", "big.txt", b"a" * (21 * MB), token).json()
    assert big["code"] == 4021 and "20 MB" in big["message"]
    empty = kb_api.upload(f"/knowledge-bases/{kb_id}/documents", "empty.txt", b"", token).json()
    assert empty["code"] == 4021
    assert kb_api.get(f"/knowledge-bases/{kb_id}", token).json()["data"]["documents"] == []
    assert list(kb_api.upload_dir.iterdir()) == []


def test_upload_rejects_type(kb_api):
    token, _ = kb_api.login("u1")
    kb_id = kb_api.create_kb(token)
    for name, content in (
        ("slides.pptx", b"PK\x03\x04 not really"),
        ("photo.png", b"\x89PNG\r\n\x1a\n"),
        ("fake.pdf", "我其实是文本".encode()),
        ("fake.docx", "我也是文本".encode()),
        ("bin.txt", b"\x00\x01\x02binary"),
    ):
        body = kb_api.upload(f"/knowledge-bases/{kb_id}/documents", name, content, token).json()
        assert body["code"] == 4020, (name, body)
    assert kb_api.get(f"/knowledge-bases/{kb_id}", token).json()["data"]["documents"] == []
    assert list(kb_api.upload_dir.iterdir()) == []


def test_upload_document_limit(kb_api, sql):
    token, user = kb_api.login("u1")
    kb_id = kb_api.create_kb(token)
    for i in range(50):
        sql.execute(
            "INSERT INTO kb_documents (document_id, kb_id, user_id, filename, file_type, size_bytes, status) "
            "VALUES (%s, %s, %s, 'x.txt', 'txt', 1, 'failed')",
            (f"doc_{i:012d}", kb_id, user["id"]),
        )
    body = kb_api.upload(f"/knowledge-bases/{kb_id}/documents", "a.txt", "你好世界".encode(), token).json()
    assert body["code"] == 4022 and "50" in body["message"]


def test_upload_to_missing_kb(kb_api):
    token, _ = kb_api.login("u1")
    body = kb_api.upload("/knowledge-bases/kb_missing/documents", "a.txt", "你好世界".encode(), token).json()
    assert body["code"] == 4040


# ---------- 删除资料 ----------


def test_delete_document(kb_api):
    token, _ = kb_api.login("u1")
    kb_id = kb_api.create_kb(token)
    doc = kb_api.upload(f"/knowledge-bases/{kb_id}/documents", "a.txt", "报销审批规则".encode(), token).json()["data"]
    kb_api.wait_documents(token, kb_id)
    assert kb_api.delete(f"/knowledge-bases/{kb_id}/documents/{doc['document_id']}", token).json()["code"] == 0
    assert kb_api.get(f"/knowledge-bases/{kb_id}", token).json()["data"]["documents"] == []
    assert kb_api.vectors.count() == 0
    again = kb_api.delete(f"/knowledge-bases/{kb_id}/documents/{doc['document_id']}", token).json()
    assert again["code"] == 4040


# ---------- 隔离 ----------


def test_other_user_gets_not_found(kb_api, tmp_path):
    token_a, _ = kb_api.login("a")
    token_b, _ = kb_api.login("b")
    kb_id = kb_api.create_kb(token_a, "A 的库")
    doc = kb_api.upload(f"/knowledge-bases/{kb_id}/documents", "a.txt", "报销审批规则".encode(), token_a).json()["data"]
    kb_api.wait_documents(token_a, kb_id)
    for resp in (
        kb_api.get(f"/knowledge-bases/{kb_id}", token_b),
        kb_api.put(f"/knowledge-bases/{kb_id}", {"name": "偷改"}, token_b),
        kb_api.delete(f"/knowledge-bases/{kb_id}", token_b),
        kb_api.upload(f"/knowledge-bases/{kb_id}/documents", "b.txt", "你好世界".encode(), token_b),
        kb_api.delete(f"/knowledge-bases/{kb_id}/documents/{doc['document_id']}", token_b),
    ):
        assert resp.json()["code"] == 4040
    assert kb_api.get("/knowledge-bases", token_b).json()["data"]["items"] == []
    detail = kb_api.get(f"/knowledge-bases/{kb_id}", token_a).json()["data"]
    assert detail["knowledge_base"]["name"] == "A 的库"
    assert [d["document_id"] for d in detail["documents"]] == [doc["document_id"]]


# ---------- 启动恢复 ----------


def test_startup_marks_processing_failed_and_clears_uploads(sql, tmp_path):
    sql.execute(
        "INSERT INTO knowledge_bases (kb_id, user_id, name) VALUES ('kb_r', 1, '甲')"
    )
    sql.execute(
        "INSERT INTO kb_documents (document_id, kb_id, user_id, filename, file_type, size_bytes, status) "
        "VALUES ('doc_r', 'kb_r', 1, 'a.pdf', 'pdf', 10, 'processing')"
    )
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "doc_r.pdf").write_bytes(b"%PDF-")

    def install(app):
        app.state.embedder = FakeEmbedder()
        app.state.vector_store = InMemoryVectorStore()

    app, *_ = build_app(kb_settings(tmp_path), before_start=install)
    with TestClient(app):
        doc = sql.one("SELECT status, fail_reason FROM kb_documents WHERE document_id = 'doc_r'")
        assert (doc["status"], doc["fail_reason"]) == ("failed", "处理被中断，请重新上传")
        assert list(uploads.iterdir()) == []


def test_real_chroma_store_is_created_by_lifespan(sql, tmp_path):
    """不注入假向量库时，lifespan 用 chroma_path 创建嵌入式 Chroma。"""

    def install(app):
        app.state.embedder = FakeEmbedder()

    app, *_ = build_app(kb_settings(tmp_path), before_start=install)
    with TestClient(app):
        from app.rag.vector_store import ChromaVectorStore

        assert isinstance(app.state.vector_store, ChromaVectorStore)
    assert (tmp_path / "chroma").is_dir()


# ---------- 知识库出题 ----------

PAY_TEXT = ("报销制度：员工出差后 30 天内提交报销申请，部门经理审批。\n\n" * 12).encode()
ATT_TEXT = ("考勤制度：每天九点前打卡，迟到三次扣半天工资。\n\n" * 12).encode()


def ready_kb(kb_api, token, files=(("报销制度.txt", PAY_TEXT), ("考勤制度.txt", ATT_TEXT))) -> tuple[str, list[str]]:
    kb_id = kb_api.create_kb(token)
    ids = []
    for name, content in files:
        body = kb_api.upload(f"/knowledge-bases/{kb_id}/documents", name, content, token).json()
        assert body["code"] == 0, body
        ids.append(body["data"]["document_id"])
    assert all(d["status"] == "ready" for d in kb_api.wait_documents(token, kb_id))
    return kb_id, ids


def kb_quiz(kb_api, token, kb_id, **payload):
    return kb_api.post(f"/knowledge-bases/{kb_id}/quiz", payload, token).json()


def test_quiz_from_whole_kb(kb_api, sql):
    token, user = kb_api.login("u1")
    kb_id, doc_ids = ready_kb(kb_api, token)
    embed_calls = len(kb_api.embedder.calls)
    body = kb_quiz(kb_api, token, kb_id, question_count=5)
    assert body["code"] == 0, body
    quiz = body["data"]
    assert quiz["source_type"] == "knowledge_base"
    assert quiz["user_input"] == ""
    types = [q["type"] for q in quiz["questions"]]
    assert (types.count("single"), types.count("multiple"), types.count("judge")) == (3, 1, 1)
    names = {"报销制度.txt", "考勤制度.txt"}
    for q in quiz["questions"]:
        assert q["sources"], q
        for s in q["sources"]:
            assert s["document_id"] in doc_ids and s["document_name"] in names
            assert s["page"] is None and 0 < len(s["quote"]) <= 120
    # 均匀抽取：两份资料都进了材料；没填重点不调 Embedding
    materials = kb_api.kb_quiz.calls[0]["materials"]
    assert "《报销制度.txt》" in materials and "《考勤制度.txt》" in materials
    assert kb_api.kb_quiz.calls[0]["focus"] == ""
    assert len(kb_api.embedder.calls) == embed_calls
    # 存为该用户的一话
    row = sql.one("SELECT user_id, user_input, question_count FROM quiz_sessions WHERE quiz_id = %s", (quiz["quiz_id"],))
    assert (row["user_id"], row["user_input"], row["question_count"]) == (user["id"], "", 5)


def test_quiz_params_validation(kb_api):
    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    assert kb_quiz(kb_api, token, kb_id, question_count=4)["code"] == 4000
    assert kb_quiz(kb_api, token, kb_id, focus="字" * 201)["code"] == 4000
    assert kb_api.kb_quiz.calls == []


def test_quiz_requires_login(kb_api):
    assert kb_api.post("/knowledge-bases/kb_x/quiz", {}).json()["code"] == 4010


def test_quiz_only_processing_documents(kb_api, sql):
    token, user = kb_api.login("u1")
    kb_id = kb_api.create_kb(token)
    sql.execute(
        "INSERT INTO kb_documents (document_id, kb_id, user_id, filename, file_type, size_bytes, status) "
        "VALUES ('doc_busy', %s, %s, 'a.pdf', 'pdf', 1, 'processing')",
        (kb_id, user["id"]),
    )
    body = kb_quiz(kb_api, token, kb_id, document_ids=["doc_busy"])
    assert body["code"] == 4023
    assert kb_quiz(kb_api, token, kb_id)["code"] == 4023
    # 空库同样 4023
    empty = kb_api.create_kb(token, "空库")
    assert kb_quiz(kb_api, token, empty)["code"] == 4023
    assert kb_api.kb_quiz.calls == []


def test_quiz_skips_documents_not_ready(kb_api, sql):
    token, user = kb_api.login("u1")
    kb_id, (pay_id, _att_id) = ready_kb(kb_api, token)
    sql.execute(
        "INSERT INTO kb_documents (document_id, kb_id, user_id, filename, file_type, size_bytes, status, fail_reason) "
        "VALUES ('doc_bad', %s, %s, '坏的.pdf', 'pdf', 1, 'failed', '文件打不开')",
        (kb_id, user["id"]),
    )
    body = kb_quiz(kb_api, token, kb_id, document_ids=[pay_id, "doc_bad"], question_count=3)
    assert body["code"] == 0, body
    sources = [s for q in body["data"]["questions"] for s in q["sources"]]
    assert {s["document_id"] for s in sources} == {pay_id}
    assert "考勤" not in kb_api.kb_quiz.calls[0]["materials"]


def test_quiz_with_document_of_other_kb_or_user(kb_api):
    token_a, _ = kb_api.login("a")
    kb_id, _ = ready_kb(kb_api, token_a)
    _, (other_doc,) = ready_kb(kb_api, token_a, files=(("别的.txt", PAY_TEXT),))
    assert kb_quiz(kb_api, token_a, kb_id, document_ids=[other_doc])["code"] == 4040
    token_b, _ = kb_api.login("b")
    _, (b_doc,) = ready_kb(kb_api, token_b, files=(("b.txt", PAY_TEXT),))
    assert kb_quiz(kb_api, token_a, kb_id, document_ids=[b_doc])["code"] == 4040
    # 用别人的库出题
    assert kb_quiz(kb_api, token_b, kb_id)["code"] == 4040
    assert kb_api.kb_quiz.calls == []


def test_focus_retrieves_related_material(kb_api):
    token, _ = kb_api.login("u1")
    # 每份资料切成十几块：top_k=12 的检索结果应全部来自讲报销的那份
    long_files = (("报销制度.txt", PAY_TEXT * 20), ("考勤制度.txt", ATT_TEXT * 20))
    kb_id, (pay_id, _) = ready_kb(kb_api, token, files=long_files)
    body = kb_quiz(kb_api, token, kb_id, focus="  报销审批 ", question_count=3)
    assert body["code"] == 0, body
    assert body["data"]["user_input"] == "报销审批"
    assert kb_api.embedder.calls[-1] == ["报销审批"]
    call = kb_api.kb_quiz.calls[0]
    assert call["focus"] == "报销审批"
    assert "《报销制度.txt》" in call["materials"] and "《考勤制度.txt》" not in call["materials"]
    assert {s["document_id"] for q in body["data"]["questions"] for s in q["sources"]} == {pay_id}


def test_focus_not_allowed_does_not_retrieve(kb_api):
    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    before = len(kb_api.embedder.calls)
    body = kb_quiz(kb_api, token, kb_id, focus="怎么制毒")
    assert body["code"] == 4003
    assert len(kb_api.embedder.calls) == before
    assert kb_api.kb_quiz.calls == []


def test_retrieval_failure_falls_back(kb_api):
    from app.rag.embedding import EmbeddingError

    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    kb_api.embedder.error = EmbeddingError("timeout")
    body = kb_quiz(kb_api, token, kb_id, focus="报销审批", question_count=3)
    assert body["code"] == 0, body
    materials = kb_api.kb_quiz.calls[0]["materials"]
    assert "《报销制度.txt》" in materials and "《考勤制度.txt》" in materials


def test_kb_quiz_never_searches_web(kb_api):
    class RecordingSearcher:
        def __init__(self):
            self.queries = []

        async def search(self, query):
            self.queries.append(query)
            return []

        async def aclose(self):
            return None

    searcher = RecordingSearcher()
    kb_api.app.state.web_searcher = searcher
    kb_api.app.state.settings.tavily_api_key = "tvly-configured"
    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    assert kb_quiz(kb_api, token, kb_id, focus="报销")["code"] == 0
    assert kb_quiz(kb_api, token, kb_id)["code"] == 0
    assert searcher.queries == []
    assert "<reference>" not in kb_api.kb_quiz.calls[0]["materials"]


def test_invented_source_triggers_conservative_retry(kb_api):
    from tests.factories import kb_quiz_dict

    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    kb_api.kb_quiz.outcomes = [kb_quiz_dict(3, source_ids=[999])]
    body = kb_quiz(kb_api, token, kb_id, question_count=3)
    assert body["code"] == 0, body
    assert [c["prompt_version"] for c in kb_api.kb_quiz.calls] == ["kb_quiz_prompt_v1", "kb_quiz_prompt_v2"]
    assert all(q["sources"] for q in body["data"]["questions"])


def test_three_failures_return_4001(kb_api, sql):
    from tests.factories import kb_quiz_dict

    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    kb_api.kb_quiz.outcomes = [kb_quiz_dict(3, source_ids=[999]), ValueError("bad json"), kb_quiz_dict(5)]
    body = kb_quiz(kb_api, token, kb_id, question_count=3)
    assert body["code"] == 4001
    assert len(kb_api.kb_quiz.calls) == 3
    assert sql.all("SELECT quiz_id FROM quiz_sessions") == []


def test_kb_quiz_flows_into_report_and_mistakes(kb_api):
    from tests.test_persistence_api import report_payload

    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    quiz = kb_quiz(kb_api, token, kb_id, question_count=5)["data"]
    # 答错第 2、4 题
    report = kb_api.post("/report/generate", report_payload(quiz, wrong=("q2", "q4")), token).json()
    assert report["code"] == 0, report
    profile = kb_api.get("/user/profile", token).json()["data"]
    assert (profile["total_xp"], profile["quiz_count"]) == (30, 1)
    items = kb_api.get("/review/mistakes", token).json()["data"]["items"]
    assert [i["question"]["id"] for i in items] == ["q2", "q4"]
    by_id = {q["id"]: q for q in quiz["questions"]}
    assert all(i["question"]["sources"] == by_id[i["question"]["id"]]["sources"] for i in items)
    assert all(i["question"]["sources"] for i in items)
    history = kb_api.get("/user/quizzes", token).json()["data"]
    assert [h["quiz_id"] for h in history["items"]] == [quiz["quiz_id"]]
    detail = kb_api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    assert detail["quiz"]["source_type"] == "knowledge_base"


def test_sources_survive_document_and_kb_deletion(kb_api):
    from tests.test_persistence_api import report_payload

    token, _ = kb_api.login("u1")
    kb_id, doc_ids = ready_kb(kb_api, token)
    quiz = kb_quiz(kb_api, token, kb_id, question_count=3)["data"]
    assert kb_api.post("/report/generate", report_payload(quiz, wrong=("q1",)), token).json()["code"] == 0
    for doc_id in doc_ids:
        assert kb_api.delete(f"/knowledge-bases/{kb_id}/documents/{doc_id}", token).json()["code"] == 0
    assert kb_api.delete(f"/knowledge-bases/{kb_id}", token).json()["code"] == 0
    detail = kb_api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    assert [q["sources"] for q in detail["quiz"]["questions"]] == [q["sources"] for q in quiz["questions"]]
    assert detail["quiz"]["source_type"] == "knowledge_base"
    assert detail["report"] is not None
    mistakes = kb_api.get("/review/mistakes", token).json()["data"]["items"]
    assert mistakes[0]["question"]["sources"][0]["document_name"] in {"报销制度.txt", "考勤制度.txt"}


# ---------- 知识库出题接入检索规划 Agent（MockDeepSeek 编排规划；出题仍用 ScriptedKbQuiz）----------

KB_TOOL, WEB_TOOL = "search_knowledge_base", "web_search"
# 每份资料切成十几块：以重点检索一次（top_k=12）的结果全部来自讲报销的那份
LONG_FILES = (("报销制度.txt", PAY_TEXT * 20), ("考勤制度.txt", ATT_TEXT * 20))
WEB_SNIPPETS = [
    SearchSnippet(title="差旅报销 百科", url="https://a", content="差旅费是出差产生的交通住宿费用。"),
    SearchSnippet(title="考勤 百科", url="https://b", content="考勤是对出勤情况的记录。"),
]


class RecordingSearcher:
    def __init__(self, results=None):
        self.queries: list[str] = []
        self.results = WEB_SNIPPETS if results is None else results

    async def search(self, query):
        self.queries.append(query)
        return self.results

    async def aclose(self):
        return None


def enable_agent(kb_api, responses: list, *, searcher: RecordingSearcher | None = None, **settings):
    """打开 Agent：规划模型换成 MockDeepSeek；searcher 不为 None 时视为配置了搜索 Key。"""
    from app.api.deps import get_retrieval_llm
    from app.llm.langchain_factory import create_chat_model

    s = kb_api.app.state.settings
    s.agent_retrieval_enabled = True
    for k, v in settings.items():
        setattr(s, k, v)
    if searcher is not None:
        kb_api.app.state.web_searcher = searcher
    mock = MockDeepSeek(responses)
    llm = create_chat_model(temperature=0.1, max_tokens=800, settings=s, http_async_client=mock.client())
    kb_api.app.dependency_overrides[get_retrieval_llm] = lambda: llm
    return mock


def bound(mock: MockDeepSeek, i: int = 0) -> list[str]:
    return [t["function"]["name"] for t in mock.requests[i].get("tools", [])]


def material_numbers(materials: str) -> list[int]:
    return [int(n) for n in re.findall(r"^\[(\d+)\]", materials, re.M)]


def test_agent_split_queries_are_merged_without_duplicates(kb_api):
    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    embed_calls = len(kb_api.embedder.calls)
    mock = enable_agent(
        kb_api,
        [
            tool_calls_response([(KB_TOOL, {"query": "报销审批"}), (KB_TOOL, {"query": "报销"}), (KB_TOOL, {"query": "考勤打卡"})]),
            text_response(),
        ],
    )
    body = kb_quiz(kb_api, token, kb_id, focus="报销审批和考勤打卡")
    assert body["code"] == 0, body
    assert bound(mock) == [KB_TOOL]  # 没配搜索 Key：只能查库
    assert kb_api.embedder.calls[embed_calls:] == [["报销审批"], ["报销"], ["考勤打卡"]]
    materials = kb_api.kb_quiz.calls[0]["materials"]
    assert "《报销制度.txt》" in materials and "《考勤制度.txt》" in materials
    # 三次检索有重叠（“报销审批”与“报销”命中同一批片段），合并后每个片段只出现一次
    previews = [m["content"] for m in mock.requests[1]["messages"] if m["role"] == "tool"]
    distinct = {n for p in previews for n in re.findall(r"^\[K(\d+)\]", p, re.M)}
    assert material_numbers(materials) == list(range(1, len(distinct) + 1))
    assert len(materials) <= kb_api.app.state.settings.kb_material_max_chars
    # 没有背景资料
    assert "background" not in kb_api.kb_quiz.calls[0]


def test_agent_not_querying_kb_falls_back_to_one_focus_retrieval(kb_api):
    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token, files=LONG_FILES)
    embed_calls = len(kb_api.embedder.calls)
    mock = enable_agent(kb_api, [text_response()])
    body = kb_quiz(kb_api, token, kb_id, focus="报销审批")
    assert body["code"] == 0, body
    assert len(mock.requests) == 1
    assert kb_api.embedder.calls[embed_calls:] == [["报销审批"]]
    materials = kb_api.kb_quiz.calls[0]["materials"]
    assert "《报销制度.txt》" in materials and "《考勤制度.txt》" not in materials


def test_retrieval_failure_after_agent_falls_back_to_spread(kb_api):
    from app.rag.embedding import EmbeddingError

    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    mock = enable_agent(kb_api, [tool_calls_response([(KB_TOOL, {"query": "报销审批"})]), text_response()])
    kb_api.embedder.error = EmbeddingError("timeout")
    body = kb_quiz(kb_api, token, kb_id, focus="报销审批")
    assert body["code"] == 0, body
    # Agent 的检索失败（结果为空）→ 以重点检索一次也失败 → 均匀抽取，两份资料都有
    assert "检索失败" in [m for m in mock.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    materials = kb_api.kb_quiz.calls[0]["materials"]
    assert "《报销制度.txt》" in materials and "《考勤制度.txt》" in materials


def test_without_focus_agent_can_only_search_web(kb_api):
    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    embed_calls = len(kb_api.embedder.calls)
    searcher = RecordingSearcher()
    mock = enable_agent(kb_api, [text_response()], searcher=searcher)
    body = kb_quiz(kb_api, token, kb_id)
    assert body["code"] == 0, body
    assert bound(mock) == [WEB_TOOL]
    assert "没有写重点" in mock.requests[0]["messages"][0]["content"]
    assert searcher.queries == []
    assert len(kb_api.embedder.calls) == embed_calls  # 均匀抽取，不调 Embedding
    materials = kb_api.kb_quiz.calls[0]["materials"]
    assert "《报销制度.txt》" in materials and "《考勤制度.txt》" in materials


def test_kb_web_switch_off_unbinds_web_tool(kb_api):
    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    searcher = RecordingSearcher()
    mock = enable_agent(kb_api, [text_response()], searcher=searcher, agent_web_in_kb_quiz=False)
    assert kb_quiz(kb_api, token, kb_id, focus="报销审批")["code"] == 0
    assert bound(mock) == [KB_TOOL]
    # 没填重点时连联网也不能用：没有可用工具，不运行规划
    assert kb_quiz(kb_api, token, kb_id)["code"] == 0
    assert len(mock.requests) == 1
    assert searcher.queries == []


def test_background_from_web_is_not_a_source(kb_api):
    token, _ = kb_api.login("u1")
    kb_id, doc_ids = ready_kb(kb_api, token)
    searcher = RecordingSearcher()
    mock = enable_agent(
        kb_api,
        [
            tool_calls_response([(KB_TOOL, {"query": "报销审批"}), (WEB_TOOL, {"query": "差旅报销 定义"})]),
            text_response(),
        ],
        searcher=searcher,
    )
    body = kb_quiz(kb_api, token, kb_id, focus="报销审批")
    assert body["code"] == 0, body
    assert bound(mock) == [KB_TOOL, WEB_TOOL]
    assert searcher.queries == ["差旅报销 定义"]
    call = kb_api.kb_quiz.calls[0]
    assert call["background"].startswith("- 差旅报销 百科\n差旅费是出差产生的交通住宿费用。")
    assert not re.search(r"^\[\d+\]", call["background"], re.M)
    assert "差旅报销 百科" not in call["materials"]
    for q in body["data"]["questions"]:
        assert q["sources"] and all(s["document_id"] in doc_ids for s in q["sources"])
        assert all("差旅" not in s["quote"] for s in q["sources"])


def test_background_is_reused_on_retry(kb_api):
    from tests.factories import kb_quiz_dict

    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token)
    searcher = RecordingSearcher()
    enable_agent(kb_api, [tool_calls_response([(WEB_TOOL, {"query": "差旅报销"})]), text_response()], searcher=searcher)
    kb_api.kb_quiz.outcomes = [kb_quiz_dict(5, source_ids=[999])]
    body = kb_quiz(kb_api, token, kb_id, focus="报销审批")
    assert body["code"] == 0, body
    assert searcher.queries == ["差旅报销"]
    calls = kb_api.kb_quiz.calls
    assert [c["prompt_version"] for c in calls] == ["kb_quiz_prompt_v1", "kb_quiz_prompt_v2"]
    assert calls[0]["background"] == calls[1]["background"] != ""
    assert calls[0]["materials"] == calls[1]["materials"]


def test_planning_error_uses_focus_retrieval_and_no_web(kb_api):
    import httpx

    token, _ = kb_api.login("u1")
    kb_id, _ = ready_kb(kb_api, token, files=LONG_FILES)
    embed_calls = len(kb_api.embedder.calls)
    searcher = RecordingSearcher()
    enable_agent(kb_api, [httpx.Response(500, json={"error": {"message": "boom"}})], searcher=searcher)
    body = kb_quiz(kb_api, token, kb_id, focus="报销审批")
    assert body["code"] == 0, body
    assert searcher.queries == []
    assert kb_api.embedder.calls[embed_calls:] == [["报销审批"]]
    assert "background" not in kb_api.kb_quiz.calls[0]
    assert "《考勤制度.txt》" not in kb_api.kb_quiz.calls[0]["materials"]


def test_agent_only_searches_selected_documents(kb_api):
    token, _ = kb_api.login("u1")
    kb_id, doc_ids = ready_kb(kb_api, token)
    enable_agent(kb_api, [tool_calls_response([(KB_TOOL, {"query": "考勤打卡"})]), text_response()])
    body = kb_quiz(kb_api, token, kb_id, focus="考勤打卡", document_ids=[doc_ids[0]])
    assert body["code"] == 0, body
    materials = kb_api.kb_quiz.calls[0]["materials"]
    assert "《报销制度.txt》" in materials and "《考勤制度.txt》" not in materials
