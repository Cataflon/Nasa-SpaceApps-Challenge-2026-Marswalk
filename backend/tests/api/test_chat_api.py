import json

from fastapi.testclient import TestClient

from app.api import main
from app.live import planning
from app.live.store import routes
from app.llm import chat

client = TestClient(main.app)


def test_chat_streams_ndjson(monkeypatch):
    monkeypatch.setattr(chat, "LLM_ENABLED", False)
    monkeypatch.setattr(planning, "get_site", lambda: None)
    routes.clear()
    r = client.post("/api/chat", json={"message": "Plan a route to the clay sample"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(l) for l in r.text.splitlines()]
    assert lines[0]["type"] == "tool_call" and lines[-1]["type"] == "done"
    routes.clear()


def test_chat_requires_message():
    assert client.post("/api/chat", json={}).status_code == 422
