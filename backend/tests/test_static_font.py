from fastapi.testclient import TestClient

from app.main import create_app

FONT_PATH = "/static/fonts/zcool-qingke-huangyou-gb1.woff"


def test_display_font_is_served():
    resp = TestClient(create_app()).get(FONT_PATH)
    assert resp.status_code == 200
    assert resp.headers["content-type"] in {"font/woff", "application/font-woff"}
    assert resp.content[:4] == b"wOFF"


def test_font_allows_miniprogram_origin():
    # wx.loadFontFace 要求字体同源或开启 CORS，小程序的来源域名是 servicewechat.com
    resp = TestClient(create_app()).get(FONT_PATH, headers={"Origin": "https://servicewechat.com"})
    assert resp.headers["access-control-allow-origin"] == "https://servicewechat.com"
