import asyncio
import json

import httpx
import pytest

from app.llm import client, templates
from app.llm.cache import key

SUMMARY = {
    "decision": "REROUTE",
    "alternative_id": "detour_north",
    "alternative_ids": ["detour_north", "wait", "return"],
    "eta_hazard_min": 16,
    "extra_min": 25,
    "o2_end_pct": 31.0,
}


def test_template_reroute():
    text = templates.render("REROUTE", alternative_id="detour_north", eta_hazard_min=16, extra_min=25, o2_end_pct=31)
    assert text == "Hazard on route in 16 min. Detour detour_north: +25 min, O₂ on arrival 31%."


def test_template_unknown_decision_does_not_crash():
    assert templates.render("FOO") == "Decision: FOO."


def test_cache_key_is_order_independent():
    assert key({"a": 1, "b": 2}) == key({"b": 2, "a": 1})


def test_explain_falls_back_when_llm_down(monkeypatch):
    monkeypatch.setattr(client, "LLM_ENABLED", True)
    monkeypatch.setattr(client, "OLLAMA_URL", "http://127.0.0.1:9")  # port închis
    monkeypatch.setattr(client.cache, "get", lambda s: None)
    out = asyncio.run(client.explain({"decision": "RETURN", "alternative_id": "return", "o2_end_pct": 58}))
    assert out["source"] == "template"


# ---------------------------------------------------------------- Ollama simulat


@pytest.fixture
def fake_ollama(monkeypatch):
    """Înlocuiește Ollama cu un răspuns fix; întoarce lista cererilor primite."""
    requests, reply = [], {}
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps(reply["content"])}})

    monkeypatch.setattr(client, "LLM_ENABLED", True)
    monkeypatch.setattr(client.cache, "get", lambda s: None)
    monkeypatch.setattr(client.cache, "put", lambda s, v: None)
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: real_client(timeout=timeout, transport=httpx.MockTransport(handler)))
    return requests, reply


def test_llm_answer_is_used(fake_ollama):
    requests, reply = fake_ollama
    reply["content"] = {"decision": "REROUTE", "alternative_id": "detour_north", "reason": " Storm reaches the route in 16 min; detour keeps 31% O2. "}
    out = asyncio.run(client.explain(SUMMARY))
    assert out == {"text": "Storm reaches the route in 16 min; detour keeps 31% O2.", "source": "llm"}

    body = requests[0]
    assert body["format"]["required"] == ["decision", "alternative_id", "reason"]
    assert body["format"]["properties"]["alternative_id"]["enum"] == SUMMARY["alternative_ids"]
    assert body["options"]["temperature"] == 0 and body["options"]["seed"] == 42
    assert body["think"] is False and body["model"] == client.OLLAMA_MODEL
    assert "in English" in body["messages"][0]["content"]


def test_llm_contradicting_decision_falls_back(fake_ollama):
    _, reply = fake_ollama
    reply["content"] = {"decision": "RETURN", "alternative_id": "return", "reason": "Go home."}
    assert asyncio.run(client.explain(SUMMARY))["source"] == "template"


def test_llm_empty_reason_falls_back(fake_ollama):
    _, reply = fake_ollama
    reply["content"] = {"decision": "REROUTE", "alternative_id": "detour_north", "reason": "  "}
    assert asyncio.run(client.explain(SUMMARY))["source"] == "template"
