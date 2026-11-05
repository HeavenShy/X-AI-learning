"""微信小程序登录凭证校验（code2Session）。

GET https://api.weixin.qq.com/sns/jscode2session?appid=APPID&secret=SECRET&js_code=JS_CODE&grant_type=authorization_code
文档：https://developers.weixin.qq.com/miniprogram/dev/server/API/user-login/api_code2session.html
接口必须在服务端调用（需要 AppSecret）；响应常以 text/plain 返回 JSON，所以按文本解析。
session_key 本期不使用，不落库、不下发。
"""

import json
import logging
from typing import Protocol

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

MOCK_OPENID = "dev-mock-openid"


class WeChatLoginError(Exception):
    def __init__(self, message: str, errcode: int | None = None):
        super().__init__(message)
        self.errcode = errcode


class WeChatAuthClient(Protocol):
    async def code_to_openid(self, code: str) -> str: ...


class WeChatAuth:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http = http_client or httpx.AsyncClient(timeout=settings.wechat_timeout_seconds)

    async def code_to_openid(self, code: str) -> str:
        s = self._settings
        if not s.wechat_app_id or not s.wechat_app_secret:
            raise WeChatLoginError("WECHAT_APP_ID / WECHAT_APP_SECRET 未配置")
        params = {
            "appid": s.wechat_app_id,
            "secret": s.wechat_app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        try:
            resp = await self._http.get(f"{s.wechat_api_base.rstrip('/')}/sns/jscode2session", params=params)
        except httpx.HTTPError as exc:
            logger.warning("code2session network error: %r", exc)
            raise WeChatLoginError("调用微信登录接口失败") from exc
        if resp.status_code != 200:
            raise WeChatLoginError(f"微信登录接口 HTTP {resp.status_code}")
        try:
            data = json.loads(resp.text)
        except ValueError as exc:
            raise WeChatLoginError("微信登录接口返回非 JSON") from exc

        errcode = data.get("errcode")
        openid = data.get("openid")
        if errcode not in (None, 0) or not openid:
            logger.warning("code2session failed: errcode=%s errmsg=%s", errcode, data.get("errmsg"))
            raise WeChatLoginError(f"微信登录失败：{data.get('errmsg', '无 openid')}", errcode=errcode)
        return str(openid)

    async def aclose(self) -> None:
        await self._http.aclose()


class MockWeChatAuth:
    """开发环境没有 AppSecret 时使用：任何 code 都登录成同一个开发用户。"""

    async def code_to_openid(self, code: str) -> str:
        return MOCK_OPENID

    async def aclose(self) -> None:
        return None
