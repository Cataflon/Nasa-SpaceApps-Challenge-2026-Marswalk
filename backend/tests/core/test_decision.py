from app.core.decision import choose
from app.core.types import Alternative


def alt(id, kind, **kw):
    base = dict(path=[], extra_min=0, o2_end_pct=50, dose_msv=0.1, risk=0.1, arrival_habitat_min=200, sunset_min=420)
    return Alternative(id=id, kind=kind, **{**base, **kw})


def demo_alternatives():
    """Scena 4 din demo: furtună locală pe traseu."""
    return [
        alt("current", "CONTINUE", risk=0.8, crosses_hazard=True),
        alt("detour_north", "REROUTE", extra_min=25, o2_end_pct=31, risk=0.12),
        alt("detour_south", "REROUTE", extra_min=40, o2_end_pct=22, risk=0.10),
        alt("wait", "WAIT", extra_min=45, o2_end_pct=30.5, risk=0.35),
        alt("return", "RETURN", o2_end_pct=58, risk=0.05, science_lost_value=1.0, science_lost=["clay_delta"]),
    ]


def test_demo_picks_north_detour():
    d = choose(demo_alternatives())
    assert (d.decision, d.alternative_id) == ("REROUTE", "detour_north")


def test_validator_rejects_low_o2():
    d = choose(demo_alternatives())
    south = next(a for a in d.alternatives if a.id == "detour_south")
    assert not south.valid and south.violations == ["O2_RESERVE"]


def test_deterministic():
    results = {(choose(demo_alternatives()).alternative_id) for _ in range(20)}
    assert results == {"detour_north"}


def test_safe_route_continues():
    d = choose([alt("current", "CONTINUE", risk=0.05), alt("detour", "REROUTE", risk=0.01)])
    assert d.decision == "CONTINUE"


def test_regional_storm_returns():
    alts = [
        alt("current", "CONTINUE", risk=0.9, crosses_hazard=True),
        alt("detour", "REROUTE", risk=0.8, crosses_hazard=True),
        alt("return", "RETURN", risk=0.2, science_lost_value=1.0),
    ]
    assert choose(alts).decision == "RETURN"


def test_no_valid_option_is_emergency():
    alts = [alt("current", "CONTINUE", crosses_hazard=True), alt("return", "RETURN", o2_end_pct=10)]
    d = choose(alts)
    assert (d.decision, d.alternative_id) == ("EMERGENCY", "return")
