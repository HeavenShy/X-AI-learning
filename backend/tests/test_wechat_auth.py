import json

import httpx
import pytest

from app.services.wechat_auth import MOCK_OPENID, MockWeChatAuth, WeChatAuth, WeChatLoginError
from tests.conftest import db_settings


def client_returning(payload: dict | None = None, *, status: int = 200, text: str | None = None, exc: Exception | None = None):
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if exc:
            raise exc
        # 微信接口常以 text/plain 返回 JSON，这里也这样模拟
        body = text if text is not None else json.dumps(payload)
        return httpx.Response(status, text=body, headers={"content-type": "text/plain"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handle)), seen


async def test_code2session_success_returns_openid_and_sends_params():
    http, seen = client_returning({"openid": "oABC", "session_key": "sk", "unionid": "u1"})
    auth = WeChatAuth(db_settings(), http_client=http)
    assert await auth.code_to_openid("the-code") == "oABC"
    req = seen[0]
    assert req.method == "GET"
    assert req.url.path == "/sns/jscode2session"
    assert dict(req.url.params) == {
        "appid": "wx-test",
        "secret": "secret-test",
        "js_code": "the-code",
        "grant_type": "authorization_code",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"errcode": 40029, "errmsg": "invalid code"},
        {"errcode": 40163, "errmsg": "code been used"},
        {"errcode": 45011, "errmsg": "api minute-quota reach limit"},
        {"errcode": -1, "errmsg": "system error"},
        {"errcode": 0},  # 没有 openid
    ],
)
async def test_code2session_errors_raise(payload):
    http, _ = client_returning(payload)
    with pytest.raises(WeChatLoginError) as ei:
        await WeChatAuth(db_settings(), http_client=http).code_to_openid("c")
    assert ei.value.errcode == payload.get("errcode")


async def test_code2session_http_error_raises():
    http, _ = client_returning(status=502, text="bad gateway")
    with pytest.raises(WeChatLoginError):
        await WeChatAuth(db_settings(), http_client=http).code_to_openid("c")


async def test_code2session_network_error_raises():
    http, _ = client_returning(exc=httpx.ConnectTimeout("timeout"))
    with pytest.raises(WeChatLoginError):
        await WeChatAuth(db_settings(), http_client=http).code_to_openid("c")


async def test_code2session_non_json_raises():
    http, _ = client_returning(text="<html>oops</html>")
    with pytest.raises(WeChatLoginError):
        await WeChatAuth(db_settings(), http_client=http).code_to_openid("c")


async def test_missing_app_secret_raises():
    with pytest.raises(WeChatLoginError):
        await WeChatAuth(db_settings(wechat_app_secret=""), http_client=client_returning({})[0]).code_to_openid("c")


async def test_mock_login_maps_every_code_to_one_dev_user():
    mock = MockWeChatAuth()
    assert await mock.code_to_openid("a") == MOCK_OPENID
    assert await mock.code_to_openid("b") == MOCK_OPENID


def test_mock_login_only_in_dev_without_secret():
    assert db_settings(app_env="dev", wechat_app_secret="").wechat_mock_login is True
    assert db_settings(app_env="dev", wechat_app_secret="s").wechat_mock_login is False
    assert db_settings(app_env="prod", wechat_app_secret="").wechat_mock_login is False
