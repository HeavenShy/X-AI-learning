from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"code": 0, "message": "ok", "data": {"status": "up"}}


def test_quiz_generate_not_implemented():
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "什么是 RAG"})
    assert resp.json()["code"] == 5001
