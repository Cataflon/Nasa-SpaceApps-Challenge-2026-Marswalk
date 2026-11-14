import json

from app.core.decision import choose
from app.core.types import Alternative, Decision
from app.llm import prompts, templates
from app.llm.cache import key
from app.llm.summary import NO_ALTERNATIVE, build_summary


def alt(id, kind, **kw):
    base = dict(path=[], extra_min=0, o2_end_pct=50, dose_msv=0.1, risk=0.1, arrival_habitat_min=200, sunset_min=420)
    return Alternative(id=id, kind=kind, **{**base, **kw})


def demo_decision():
    """Scena 4 din demo: furtună locală pe traseu (aceeași ca în tests/core/test_decision.py)."""
    return choose([
        alt("current", "CONTINUE", risk=0.8, crosses_hazard=True),
        alt("detour_north", "REROUTE", extra_min=25.4, o2_end_pct=31.04, dose_msv=0.2049, risk=0.12),
        alt("detour_south", "REROUTE", extra_min=40, o2_end_pct=22, risk=0.10),
        alt("wait", "WAIT", extra_min=45, o2_end_pct=30.5, risk=0.35),
        alt("return", "RETURN", o2_end_pct=58, risk=0.05, science_lost_value=1.0, science_lost=["clay_delta"]),
    ])


def demo_summary():
    return build_summary(demo_decision(), t_min=72.3, hazard_kind="local_storm", eta_hazard_min=16.2)


def test_demo_summary_content():
    s = demo_summary()
    assert (s["decision"], s["alternative_id"]) == ("REROUTE", "detour_north")
    assert s["alternative_ids"] == ["detour_north", "wait", "return"]
    assert {"id": "detour_south", "why": ["O2_RESERVE"]} in s["rejected"]
    assert {"id": "current", "why": ["HAZARD"]} in s["rejected"]
    assert s["hazard"] == "local_storm"


def test_numbers_are_rounded():
    s = demo_summary()
    assert (s["t_min"], s["eta_hazard_min"], s["extra_min"]) == (72, 16, 25)
    assert s["o2_end_pct"] == 31.0
    assert s["dose_msv"] == 0.2


def test_same_input_same_cache_key():
    assert key(demo_summary()) == key(demo_summary())


def test_no_none_values():
    s = build_summary(demo_decision(), t_min=72)  # fără pericol și fără ETA
    assert None not in s.values()
    assert "hazard" not in s and "eta_hazard_min" not in s


def test_template_renders_from_summary():
    s = demo_summary()
    text = templates.render(s["decision"], **s)
    assert "16 min" in text and "+25 min" in text and "31%" in text


def test_emergency_with_invalid_return_is_in_enum():
    d = choose([alt("current", "CONTINUE", crosses_hazard=True), alt("return", "RETURN", o2_end_pct=10)])
    s = build_summary(d, t_min=100)
    assert s["decision"] == "EMERGENCY" and s["alternative_id"] == "return"
    assert "return" in s["alternative_ids"]
    enum = prompts.response_schema(s["alternative_ids"])["properties"]["alternativa_id"]["enum"]
    assert s["alternative_id"] in enum


def test_emergency_without_any_route_uses_none():
    d = Decision("EMERGENCY", None, "NO_VALID_OPTION", [alt("current", "CONTINUE", crosses_hazard=True)])
    validated = choose(d.alternatives)  # completează valid/violations
    s = build_summary(Decision("EMERGENCY", None, "NO_VALID_OPTION", validated.alternatives), t_min=100)
    assert s["alternative_id"] == NO_ALTERNATIVE
    assert s["alternative_ids"] == [NO_ALTERNATIVE]
    assert "o2_end_pct" not in s
    assert templates.render(s["decision"], **s).startswith("Nicio variantă")


def test_summary_is_compact():
    assert len(prompts.user_prompt(demo_summary())) < 1500
    json.dumps(demo_summary())  # serializabil
