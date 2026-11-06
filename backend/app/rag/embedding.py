"""文本向量化：硅基流动 /embeddings（OpenAI 兼容接口），模型 BAAI/bge-m3，1024 维。

POST {base_url}/embeddings，Authorization: Bearer <key>
请求体 {"model", "input": [...], "encoding_format": "float"}；input 数组单次最多 32 条。
文档：https://docs.siliconflow.com/en/api-reference/embeddings/create-embeddings
所有失败都转成 EmbeddingError；异常信息与日志里只出现状态码，不出现 Key 和请求头。
"""

from typing import Protocol

import httpx

from app.core.config import Settings


class EmbeddingError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class SiliconFlowEmbedder:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http = http_client or httpx.AsyncClient(timeout=settings.embedding_timeout_seconds)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """按 embedding_batch_size 分批请求，返回与 texts 一一对应的向量。"""
        if not self._settings.siliconflow_api_key:
            raise EmbeddingError("SILICONFLOW_API_KEY 未配置")
        size = max(1, self._settings.embedding_batch_size)
        vectors: list[list[float]] = []
        for i in range(0, len(texts), size):
            vectors += await self._embed_batch(texts[i : i + size])
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        s = self._settings
        try:
            resp = await self._http.post(
                f"{s.siliconflow_base_url.rstrip('/')}/embeddings",
                json={"model": s.embedding_model, "input": batch, "encoding_format": "float"},
                headers={"Authorization": f"Bearer {s.siliconflow_api_key}"},
                timeout=s.embedding_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise EmbeddingError(f"Embedding 请求超时（{type(exc).__name__}）") from None
        except httpx.HTTPError as exc:
            # 只保留异常类型：httpx 的异常对象会挂着带 Authorization 头的 request
            raise EmbeddingError(f"Embedding 网络错误（{type(exc).__name__}）") from None
        if resp.status_code != 200:
            raise EmbeddingError(f"Embedding HTTP {resp.status_code}", status=resp.status_code)
        try:
            payload = resp.json()
        except ValueError:
            raise EmbeddingError("Embedding 返回非 JSON", status=resp.status_code) from None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or len(data) != len(batch):
            raise EmbeddingError(
                f"Embedding 返回条数不符（期望 {len(batch)}）", status=resp.status_code
            )
        try:
            ordered = sorted(data, key=lambda item: int(item["index"]))
            vectors = [[float(x) for x in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError):
            raise EmbeddingError("Embedding 响应格式不对", status=resp.status_code) from None
        if [int(item["index"]) for item in ordered] != list(range(len(batch))):
            raise EmbeddingError("Embedding 返回的 index 不连续", status=resp.status_code)
        if any(len(v) != s.embedding_dimensions for v in vectors):
            raise EmbeddingError(f"Embedding 维度不是 {s.embedding_dimensions}", status=resp.status_code)
        return vectors

    async def aclose(self) -> None:
        await self._http.aclose()
