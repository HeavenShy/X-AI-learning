from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.core.auth import TokenError, create_token, decode_token, optional_user_id, require_user_id
from app.main import create_app
from tests.conftest import db_settings

SETTINGS = db_settings()


def test_token_round_trip():
    token = create_token(42, "openid-42", SETTINGS)
    claims = decode_token(token, SETTINGS)
    assert claims.user_id == 42
    assert claims.openid == "openid-42"


def test_token_expires_after_configured_days():
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    token = create_token(1, "o", SETTINGS, now=now)
    raw = jwt.decode(token, options={"verify_signature": False})
    assert raw["exp"] - raw["iat"] == SETTINGS.jwt_expire_days * 86400
    assert raw["sub"] == "1"


def test_expired_token_is_rejected():
    past = datetime.now(timezone.utc) - timedelta(days=SETTINGS.jwt_expire_days + 1)
    with pytest.raises(TokenError):
        decode_token(create_token(1, "o", SETTINGS, now=past), SETTINGS)


def test_token_signed_with_other_key_is_rejected():
    other = db_settings(jwt_secret="another-secret-another-secret-another-secret")
    with pytest.raises(TokenError):
        decode_token(create_token(1, "o", other), SETTINGS)


@pytest.mark.parametrize("bad", ["", "not-a-jwt", "a.b.c"])
def test_garbage_token_is_rejected(bad):
    with pytest.raises(TokenError):
        decode_token(bad, SETTINGS)


def test_token_without_user_id_is_rejected():
    token = jwt.encode({"openid": "o", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                       SETTINGS.jwt_signing_key, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_token(token, SETTINGS)


def test_production_requires_jwt_secret():
    with pytest.raises(RuntimeError):
        _ = db_settings(jwt_secret="", app_env="prod").jwt_signing_key


# ---------- 依赖：可选鉴权 / 必须鉴权 ----------

def _probe_client() -> TestClient:
    app = create_app(SETTINGS)
    router = APIRouter()

    @router.get("/_probe/optional")
    async def opt(user_id: int | None = Depends(optional_user_id)):
        return {"user_id": user_id}

    @router.get("/_probe/required")
    async def req(user_id: int = Depends(require_user_id)):
        return {"user_id": user_id}

    app.include_router(router)
    return TestClient(app)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_optional_auth_without_header_is_anonymous():
    assert _probe_client().get("/_probe/optional").json() == {"user_id": None}


def test_optional_auth_reads_user_id():
    resp = _probe_client().get("/_probe/optional", headers=_auth(create_token(7, "o", SETTINGS)))
    assert resp.json() == {"user_id": 7}


def test_optional_auth_treats_invalid_token_as_anonymous():
    resp = _probe_client().get("/_probe/optional", headers=_auth("broken"))
    assert resp.json() == {"user_id": None}


def test_required_auth_without_token_returns_4010():
    resp = _probe_client().get("/_probe/required")
    assert resp.status_code == 401
    assert resp.json() == {"code": 4010, "message": "登录已失效，请重新登录", "data": None}


def test_required_auth_rejects_invalid_token():
    resp = _probe_client().get("/_probe/required", headers=_auth("broken"))
    assert resp.status_code == 401
    assert resp.json()["code"] == 4010


@pytest.mark.parametrize("header", ["Token abc", "Bearer", "bearer  "])
def test_required_auth_rejects_malformed_header(header):
    resp = _probe_client().get("/_probe/required", headers={"Authorization": header})
    assert resp.json()["code"] == 4010


def test_required_auth_accepts_valid_token():
    resp = _probe_client().get("/_probe/required", headers=_auth(create_token(9, "o", SETTINGS)))
    assert resp.json() == {"user_id": 9}
