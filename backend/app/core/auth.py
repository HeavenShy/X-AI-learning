"""JWT 会话令牌与鉴权依赖。

- optional_user_id：出题 / 报告接口用。没有或无效的 token 视为匿名，不报错。
- require_user_id：/user/* 接口用。没有或无效时返回 HTTP 401 + code 4010。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Request

from app.core.config import Settings
from app.core.exceptions import BizError, ErrorCode

ALGORITHM = "HS256"
MSG_UNAUTHORIZED = "登录已失效，请重新登录"


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    openid: str


def create_token(user_id: int, openid: str, settings: Settings, *, now: datetime | None = None) -> str:
    issued = now or datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "openid": openid,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(days=settings.jwt_expire_days)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=ALGORITHM)


def decode_token(token: str, settings: Settings) -> TokenClaims:
    try:
        payload = jwt.decode(
            token, settings.jwt_signing_key, algorithms=[ALGORITHM], options={"require": ["sub", "exp"]}
        )
        return TokenClaims(user_id=int(payload["sub"]), openid=str(payload.get("openid", "")))
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise TokenError(str(exc)) from exc


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _settings(request: Request) -> Settings:
    return request.app.state.settings


async def optional_user_id(request: Request) -> int | None:
    token = _bearer_token(request)
    if not token:
        return None
    try:
        return decode_token(token, _settings(request)).user_id
    except TokenError:
        return None


async def require_user_id(request: Request) -> int:
    token = _bearer_token(request)
    if not token:
        raise BizError(ErrorCode.UNAUTHORIZED, MSG_UNAUTHORIZED, http_status=401)
    try:
        return decode_token(token, _settings(request)).user_id
    except TokenError as exc:
        raise BizError(ErrorCode.UNAUTHORIZED, MSG_UNAUTHORIZED, http_status=401) from exc
