"""数据库相关测试的公共夹具。

测试库默认是 Docker 里的 yhyd_test（127.0.0.1:3307），可用 TEST_MYSQL_* 环境变量覆盖。
连不上测试库时，依赖数据库的用例自动跳过，其余离线用例照常运行。
"""

import asyncio
import os

import pymysql
import pytest

from app.core.config import Settings
from app.core.db import TABLES, init_schema
from tests.llm_mock import test_settings

DB_PARAMS = dict(
    host=os.getenv("TEST_MYSQL_HOST", "127.0.0.1"),
    port=int(os.getenv("TEST_MYSQL_PORT", "3307")),
    user=os.getenv("TEST_MYSQL_USER", "yhyd"),
    password=os.getenv("TEST_MYSQL_PASSWORD", "yhyd_dev_2026"),
    database=os.getenv("TEST_MYSQL_DATABASE", "yhyd_test"),
)
assert DB_PARAMS["database"].endswith("_test"), "测试会清空数据，只能指向 *_test 库"


def _db_reachable() -> bool:
    try:
        pymysql.connect(**DB_PARAMS, connect_timeout=2).close()
        return True
    except pymysql.MySQLError:
        return False


DB_AVAILABLE = _db_reachable()


def db_settings(**overrides) -> Settings:
    base = dict(
        mysql_host=DB_PARAMS["host"],
        mysql_port=DB_PARAMS["port"],
        mysql_user=DB_PARAMS["user"],
        mysql_password=DB_PARAMS["password"],
        mysql_database=DB_PARAMS["database"],
        mysql_pool_min=1,
        mysql_pool_max=3,
        jwt_secret="test-jwt-secret-0123456789abcdef0123456789",
        app_env="test",
        wechat_app_id="wx-test",
        wechat_app_secret="secret-test",
    )
    base.update(overrides)
    return test_settings(**base)


class SyncDB:
    """测试里直接查库 / 造数据用的同步连接（不与应用的事件循环纠缠）。"""

    def __init__(self):
        self.conn = pymysql.connect(**DB_PARAMS, autocommit=True, cursorclass=pymysql.cursors.DictCursor)

    def all(self, sql: str, args=None) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def one(self, sql: str, args=None) -> dict | None:
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def execute(self, sql: str, args=None) -> int:
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.lastrowid

    def truncate_all(self):
        for t in TABLES:
            self.execute(f"TRUNCATE TABLE {t}")

    def close(self):
        self.conn.close()


@pytest.fixture
def sql():
    """干净的测试库：建表（幂等）并清空所有表。"""
    if not DB_AVAILABLE:
        pytest.skip("测试库不可用（docker 启动 yhyd-mysql 后重跑）")
    asyncio.run(_init())
    db = SyncDB()
    db.truncate_all()
    yield db
    db.close()


async def _init():
    from app.core.db import Database

    db = await Database.connect(db_settings())
    try:
        await init_schema(db)
    finally:
        await db.close()


# ---------- 接口测试：带真实测试库的 App ----------


class FakeWeChat:
    """code → openid：默认 'o-<code>'；code 为 'bad' 时模拟微信返回错误。"""

    def __init__(self):
        self.codes: list[str] = []

    async def code_to_openid(self, code: str) -> str:
        from app.services.wechat_auth import WeChatLoginError

        self.codes.append(code)
        if code == "bad":
            raise WeChatLoginError("invalid code", errcode=40029)
        return f"o-{code}"

    async def aclose(self) -> None:
        return None


class AlwaysQuiz:
    """出题假模型：按请求题量返回合法题库。"""

    async def generate(self, *, question_count: int, **_):
        from tests.factories import generated_quiz

        return generated_quiz(question_count)


class ScriptedReport:
    """报告假模型：outcomes 为空时总是成功；元素是异常则抛出。"""

    def __init__(self):
        self.outcomes: list = []
        self.calls = 0

    async def generate(self, **_):
        from tests.report_factories import generated_report_dict
        from app.llm.output_schemas import GeneratedReport

        self.calls += 1
        if self.outcomes:
            o = self.outcomes.pop(0)
            if isinstance(o, BaseException):
                raise o
            return o
        return GeneratedReport.model_validate(generated_report_dict())


class Api:
    def __init__(self, client, wechat: FakeWeChat, report_gen: ScriptedReport):
        self.client = client
        self.wechat = wechat
        self.report_gen = report_gen

    def login(self, code: str = "u1") -> tuple[str, dict]:
        body = self.client.post("/api/v1/user/login", json={"code": code}).json()
        assert body["code"] == 0, body
        return body["data"]["token"], body["data"]["user"]

    @staticmethod
    def auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def get(self, path: str, token: str | None = None, **kw):
        return self.client.get(f"/api/v1{path}", headers=self.auth(token) if token else {}, **kw)

    def post(self, path: str, json: dict, token: str | None = None):
        return self.client.post(f"/api/v1{path}", json=json, headers=self.auth(token) if token else {})

    def put(self, path: str, json: dict, token: str | None = None):
        return self.client.put(f"/api/v1{path}", json=json, headers=self.auth(token) if token else {})

    def delete(self, path: str, token: str | None = None):
        return self.client.delete(f"/api/v1{path}", headers=self.auth(token) if token else {})

    def upload(self, path: str, filename: str, content: bytes, token: str | None = None):
        return self.client.post(
            f"/api/v1{path}", files={"file": (filename, content)}, headers=self.auth(token) if token else {}
        )


def build_app(settings: Settings, *, before_start=None):
    """带真实测试库的 App 与假模型；before_start(app, ctx) 可在启动前放入更多假实现。"""
    from app.api.deps import get_quiz_service, get_report_service, get_wechat_auth
    from app.main import create_app
    from app.services.quiz_service import QuizService
    from app.services.report_service import ReportService
    from app.utils.content_filter import ContentFilter, get_content_filter

    app = create_app(settings)
    wechat = FakeWeChat()
    report_gen = ScriptedReport()
    words = ContentFilter(["制毒", "傻瓜蛋"])
    quiz_service = QuizService(AlwaysQuiz(), settings=settings, content_filter=words)
    report_service = ReportService(report_gen, settings=settings, content_filter=words)
    app.dependency_overrides[get_wechat_auth] = lambda: wechat
    app.dependency_overrides[get_content_filter] = lambda: words
    app.dependency_overrides[get_quiz_service] = lambda: quiz_service
    app.dependency_overrides[get_report_service] = lambda: report_service
    app.state.content_filter = words
    if before_start is not None:
        before_start(app)
    return app, wechat, report_gen


@pytest.fixture
def api(sql):
    from fastapi.testclient import TestClient

    app, wechat, report_gen = build_app(db_settings())
    with TestClient(app) as client:
        assert app.state.db is not None, "lifespan 未连上测试库"
        yield Api(client, wechat, report_gen)


# ---------- 知识库接口测试：开启知识库，Embedding / 向量库用假实现 ----------


class ScriptedKbQuiz:
    """知识库出题假模型：outcomes 为空时按材料里的真实编号轮流标出处；元素是异常则抛出，是 dict 则作为输出。"""

    def __init__(self):
        self.outcomes: list = []
        self.calls: list[dict] = []

    async def generate(self, *, materials: str, question_count: int, **kw):
        import re

        from app.llm.output_schemas import GeneratedKbQuiz
        from tests.factories import kb_quiz_dict

        self.calls.append({"materials": materials, "question_count": question_count, **kw})
        if self.outcomes:
            o = self.outcomes.pop(0)
            if isinstance(o, BaseException):
                raise o
            return GeneratedKbQuiz.model_validate(o)
        numbers = [int(n) for n in re.findall(r"^\[(\d+)\]", materials, re.M)]
        return GeneratedKbQuiz.model_validate(
            kb_quiz_dict(question_count, source_ids=lambda i: [numbers[i % len(numbers)]])
        )


class KbApi(Api):
    def __init__(self, client, wechat, report_gen, *, app, embedder, vectors, upload_dir, kb_quiz):
        super().__init__(client, wechat, report_gen)
        self.app = app
        self.embedder = embedder
        self.vectors = vectors
        self.upload_dir = upload_dir
        self.kb_quiz = kb_quiz

    def create_kb(self, token: str, name: str = "公司新人考核") -> str:
        body = self.post("/knowledge-bases", {"name": name}, token).json()
        assert body["code"] == 0, body
        return body["data"]["kb_id"]

    def wait_documents(self, token: str, kb_id: str, timeout: float = 10.0) -> list[dict]:
        """轮询详情直到没有处理中的资料（后台任务跑在 TestClient 的事件循环里）。"""
        import time

        deadline = time.monotonic() + timeout
        while True:
            docs = self.get(f"/knowledge-bases/{kb_id}", token).json()["data"]["documents"]
            if all(d["status"] != "processing" for d in docs) or time.monotonic() > deadline:
                return docs
            time.sleep(0.05)


def kb_settings(tmp_path, **overrides) -> Settings:
    base = dict(
        siliconflow_api_key="sk-sf-test",
        kb_upload_dir=str(tmp_path / "uploads"),
        chroma_path=str(tmp_path / "chroma"),
    )
    base.update(overrides)
    return db_settings(**base)


@pytest.fixture
def kb_api(sql, tmp_path):
    from fastapi.testclient import TestClient

    from app.rag.vector_store import InMemoryVectorStore
    from tests.kb_files import FakeEmbedder

    from app.api.deps import get_kb_quiz_generator

    embedder = FakeEmbedder()
    vectors = InMemoryVectorStore()
    kb_quiz = ScriptedKbQuiz()

    def install(app):
        app.state.embedder = embedder
        app.state.vector_store = vectors
        app.dependency_overrides[get_kb_quiz_generator] = lambda: kb_quiz

    settings = kb_settings(tmp_path)
    app, wechat, report_gen = build_app(settings, before_start=install)
    with TestClient(app) as client:
        assert app.state.kb_ingestor is not None, "知识库未开启"
        yield KbApi(
            client, wechat, report_gen, app=app, embedder=embedder, vectors=vectors,
            upload_dir=tmp_path / "uploads", kb_quiz=kb_quiz,
        )
