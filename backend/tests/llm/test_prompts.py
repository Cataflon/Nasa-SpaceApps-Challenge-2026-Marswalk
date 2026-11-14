import asyncio
import json

import pytest

from app.llm import client, prompts
from app.llm.samples import situations

S = dict(situations())


def test_facts_start_with_the_action_and_use_words():
    text = prompts.facts(S["local storm A"])
    lines = text.splitlines()
    assert lines[0] == "Action: take the north detour."
    assert "local dust storm reaches your route in 16 min" in text
    assert "O2 when back at the habitat: 31% (above the 30% safety reserve)" in text
    assert "south detour (O2 below the safety reserve)" in text
    assert lines[-1] == "Copy exactly: decision=REROUTE, alternative_id=detour_north."
    # Fără chei codate care încurcă modelul.
    for raw in ("t_min", "eta_hazard_min", "o2_end_pct", "O2_RESERVE", "detour_north)", "reason_code"):
        assert raw not in text.replace("alternative_id=detour_north", "")


def test_emergency_says_below_reserve_and_why():
    text = prompts.facts(S["emergency A"])
    assert "BELOW the 30% safety reserve" in text
    assert "Even the return to the habitat breaks a limit: O2 below the safety reserve." in text


def test_problems_are_not_route_hazards():
    assert "Problem: suit leak detected." in prompts.facts(S["suit leak A"])


@pytest.mark.parametrize("alt_id,name", [
    ("detour_north", "north detour"), ("detour_east", "east detour"), ("wait", "waiting"),
    ("return", "return to the habitat"), ("current", "current route"), ("none", "no route"),
])
def test_alt_names(alt_id, name):
    assert prompts.alt_name(alt_id) == name


def test_examples_follow_the_rules():
    for example, reason in prompts.EXAMPLES:
        assert len(reason.split()) <= 25, reason
        assert reason.split(":")[0].split()[0] in ("Take", "Return", "Stop", "Head"), reason
        numbers = [w.strip(".,%") for w in reason.split() if any(c.isdigit() for c in w)]
        facts = prompts.facts(example)
        assert all(n in facts for n in numbers), (numbers, facts)


def test_messages_layout():
    msgs = prompts.messages(S["local storm A"])
    assert msgs[0]["role"] == "system"
    assert [m["role"] for m in msgs[1:-1]] == ["user", "assistant"] * len(prompts.EXAMPLES)
    assert msgs[-1] == {"role": "user", "content": prompts.facts(S["local storm A"])}
    for m in msgs[2:-1:2]:
        assert set(json.loads(m["content"])) == {"decision", "alternative_id", "reason"}


def test_cache_key_depends_on_prompt_version_and_model(monkeypatch):
    seen = []
    monkeypatch.setattr(client, "LLM_ENABLED", True)
    monkeypatch.setattr(client.cache, "get", lambda key: seen.append(key) or {"text": "cached"})
    out = asyncio.run(client.explain(S["local storm A"]))
    assert out["source"] == "cache"
    assert seen[0]["_prompt"] == prompts.PROMPT_VERSION and seen[0]["_model"] == client.OLLAMA_MODEL
