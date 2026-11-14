import asyncio

from app.llm import templates
from app.llm.cache import key


def test_template_reroute():
    text = templates.render("REROUTE", alternative_id="detour_north", eta_hazard_min=16, extra_min=25, o2_end_pct=31)
    assert "16 min" in text and "31%" in text


def test_template_unknown_decision_does_not_crash():
    assert templates.render("FOO") == "Decizie: FOO."


def test_cache_key_is_order_independent():
    assert key({"a": 1, "b": 2}) == key({"b": 2, "a": 1})


def test_explain_falls_back_when_llm_down(monkeypatch):
    from app.llm import client

    monkeypatch.setattr(client, "LLM_ENABLED", True)
    monkeypatch.setattr(client, "OLLAMA_URL", "http://127.0.0.1:9")  # port închis
    monkeypatch.setattr(client.cache, "get", lambda s: None)
    out = asyncio.run(client.explain({"decision": "RETURN", "alternative_id": "return", "o2_end_pct": 58}))
    assert out["source"] == "template"
