from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应结构：{code, message, data}"""

    code: int = 0
    message: str = "ok"
    data: T | None = None


def ok(data: T) -> ApiResponse[T]:
    return ApiResponse(data=data)
