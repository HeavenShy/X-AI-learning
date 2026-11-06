import json
import logging

import httpx
import pytest

from app.rag.embedding import EmbeddingError, SiliconFlowEmbedder
from tests.llm_mock import test_settings

KEY = "sk-sf-SECRET-KEY-123"
DIM = 1024


def vec(i: int) -> list[float]:
    return [float(i)] * DIM


def ok_payload(n: int, *, start: int = 0, reverse: bool = False) -> dict:
    items = [{"object": "embedding", "index": i, "embedding": vec(start + i)} for i in range(n)]
    if reverse:
        items.reverse()
    return {"object": "list", "model": "BAAI/bge-m3", "data": items, "usage": {"total_tokens": 5}}


def embedder_with(handler, **overrides) -> tuple[SiliconFlowEmbedder, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    settings = test_settings(siliconflow_api_key=KEY, **overrides)
    return SiliconFlowEmbedder(settings, http_client=http), seen


async def test_embed_sends_siliconflow_contract():
    embedder, seen = embedder_with(lambda r: httpx.Response(200, json=ok_payload(2)))
    vectors = await embedder.embed(["甲", "乙"])
    assert vectors == [vec(0), vec(1)]
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == "https://api.siliconflow.cn/v1/embeddings"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(req.content) == {"model": "BAAI/bge-m3", "input": ["甲", "乙"], "encoding_format": "float"}
    assert KEY not in req.content.decode()


async def test_embed_splits_into_batches_and_keeps_order():
    def handle(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        start = int(texts[0])
        return httpx.Response(200, json=ok_payload(len(texts), start=start))

    embedder, seen = embedder_with(handle, embedding_batch_size=2)
    texts = [str(i) for i in range(5)]
    vectors = await embedder.embed(texts)
    assert [json.loads(r.content)["input"] for r in seen] == [["0", "1"], ["2", "3"], ["4"]]
    assert vectors == [vec(i) for i in range(5)]


async def test_embed_sorts_by_index():
    embedder, _ = embedder_with(lambda r: httpx.Response(200, json=ok_payload(3, reverse=True)))
    assert await embedder.embed(["a", "b", "c"]) == [vec(0), vec(1), vec(2)]


async def test_embed_empty_input_makes_no_request():
    embedder, seen = embedder_with(lambda r: httpx.Response(200, json=ok_payload(0)))
    assert await embedder.embed([]) == []
    assert seen == []


@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
async def test_http_errors_raise(status, caplog):
    caplog.set_level(logging.DEBUG)
    embedder, _ = embedder_with(lambda r: httpx.Response(status, json={"message": "nope"}))
    with pytest.raises(EmbeddingError) as info:
        await embedder.embed(["a"])
    assert info.value.status == status
    assert KEY not in str(info.value)
    assert KEY not in caplog.text


async def test_timeout_raises_without_key(caplog):
    caplog.set_level(logging.DEBUG)

    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    embedder, _ = embedder_with(handle)
    with pytest.raises(EmbeddingError) as info:
        await embedder.embed(["a"])
    assert "超时" in str(info.value)
    assert info.value.__cause__ is None
    assert KEY not in str(info.value)
    assert KEY not in caplog.text


async def test_network_error_raises_without_key():
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    embedder, _ = embedder_with(handle)
    with pytest.raises(EmbeddingError) as info:
        await embedder.embed(["a"])
    assert "ConnectError" in str(info.value)
    assert KEY not in str(info.value)
    # from None：异常链里不挂着带 Authorization 头的 httpx 请求
    assert info.value.__cause__ is None


async def test_non_json_raises():
    embedder, _ = embedder_with(lambda r: httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(EmbeddingError, match="非 JSON"):
        await embedder.embed(["a"])


@pytest.mark.parametrize(
    "payload",
    [
        ok_payload(1),  # 条数少了
        ok_payload(3),  # 条数多了
        {"data": "x"},
        {"oops": True},
        [],
    ],
)
async def test_wrong_count_or_shape_raises(payload):
    embedder, _ = embedder_with(lambda r: httpx.Response(200, json=payload))
    with pytest.raises(EmbeddingError):
        await embedder.embed(["a", "b"])


async def test_wrong_dimension_raises():
    payload = {"data": [{"index": 0, "embedding": [0.1] * 768}]}
    embedder, _ = embedder_with(lambda r: httpx.Response(200, json=payload))
    with pytest.raises(EmbeddingError, match="维度"):
        await embedder.embed(["a"])


async def test_bad_items_raise():
    payload = {"data": [{"index": 0, "embedding": ["x"] * DIM}]}
    embedder, _ = embedder_with(lambda r: httpx.Response(200, json=payload))
    with pytest.raises(EmbeddingError):
        await embedder.embed(["a"])


async def test_duplicate_index_raises():
    payload = {"data": [{"index": 0, "embedding": vec(0)}, {"index": 0, "embedding": vec(1)}]}
    embedder, _ = embedder_with(lambda r: httpx.Response(200, json=payload))
    with pytest.raises(EmbeddingError):
        await embedder.embed(["a", "b"])


async def test_missing_key_raises_without_request():
    seen = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)))
    embedder = SiliconFlowEmbedder(test_settings(), http_client=http)
    with pytest.raises(EmbeddingError):
        await embedder.embed(["a"])
    assert seen == []
