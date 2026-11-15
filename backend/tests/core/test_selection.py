"""F4: validatorul V1-V8, scorul normalizat, histerezisul și EMERGENCY (ARHITECTURA_RUTARE_V2 §7, §9)."""

import pytest

from app.core import selection as sel
from app.core.types import Alternative, Limits
from app.core.validator import violations


def alt(id, kind, **kw):
    base = dict(path=[(0, 0), (0, 1)], extra_min=0, o2_end_pct=60, dose_msv=0.05, risk=0.0,
                arrival_habitat_min=200, sunset_min=600)
    return Alternative(id=id, kind=kind, **{**base, **kw})


def test_new_invariants_v5_to_v8():
    L = Limits()
    assert violations(alt("a", "REROUTE", exposure_over_limit=True), L) == ["HAZARD"]
    assert violations(alt("a", "REROUTE", beyond_pnr=True), L) == ["NO_RETURN_POINT"]
    assert violations(alt("r", "RETURN", beyond_pnr=True), L) == []  # V6 nu se aplică variantelor RETURN
    assert violations(alt("a", "REROUTE", beyond_pnr=True, phase="INBOUND"), L) == []  # nici pe întoarcere
    assert violations(alt("a", "REROUTE", off_map=True), L) == ["OFF_MAP"]
    assert violations(alt("a", "REROUTE", refuge_unusable=True), L) == ["NO_SHELTER"]
    assert violations(alt("a", "REROUTE", o2_end_pct=29.9, arrival_habitat_min=580, max_slope_deg=20.1,
                          dose_msv=1.1), L) == ["O2_RESERVE", "DAYLIGHT", "SLOPE", "DOSE"]


def test_weights_and_terms_are_normalized():
    for w in sel.WEIGHTS.values():
        assert sum(w.values()) == pytest.approx(1.0)
    worst = alt("w", "REROUTE", exposure_min=50, o2_end_pct=0, extra_min=500, dose_msv=5, science_lost_value=1)
    best = alt("b", "REROUTE", o2_end_pct=100, dose_msv=0.0)
    for preset in sel.WEIGHTS:
        assert sel.score(worst, preset) == pytest.approx(1.0)
        assert sel.score(best, preset) == pytest.approx(0.0)
    lost = alt("l", "RETURN", science_lost_value=1.0, o2_end_pct=100, dose_msv=0.0)
    # ponderea științei e aliniată cu costmap.PRESETS["science"]["w_science"] = 0,4 (§7, „aliniate cu decision.py”)
    assert sel.score(lost, "science") == pytest.approx(0.40)
    assert sel.WEIGHTS["safe"]["science"] == pytest.approx(0.15)
    assert sel.WEIGHTS["safe"]["risk"] / sel.WEIGHTS["safe"]["o2"] == pytest.approx(0.55 / 0.25)  # proporțiile §7
    assert sel.score(lost, "science", phase="INBOUND") == 0.0  # pe întoarcere știința pierdută = 0


def test_ties_break_on_strategy_priority_then_id():
    a = [alt("current", "CONTINUE", risk=0.9, exposure_min=9), alt("return", "RETURN", o2_end_pct=70),
         alt("detour_north", "REROUTE", o2_end_pct=70), alt("detour_free", "REROUTE", o2_end_pct=70)]
    d = sel.select(a)
    assert d.alternative_id == "detour_north"  # același scor: ocolirea are prioritate față de detour_free și return


def test_safe_current_route_continues():
    d = sel.select([alt("current", "CONTINUE"), alt("detour_north", "REROUTE", o2_end_pct=99)])
    assert (d.decision, d.reason_code) == ("CONTINUE", "ROUTE_OK")


def test_hysteresis_needs_delta_and_dwell():
    current = alt("current", "CONTINUE", risk=0.4, halo_integral=0.8, o2_end_pct=60)  # valid, dar cu risc
    slightly = alt("detour_north", "REROUTE", risk=0.38, halo_integral=0.76, o2_end_pct=60)
    d = sel.select([current, slightly], sel.Context(t_now=50))
    assert (d.decision, d.reason_code) == ("CONTINUE", "HYSTERESIS")  # câștig < 12 %
    much = alt("detour_north", "REROUTE", o2_end_pct=60)
    ctx = sel.Context(t_now=50, last_switch_t=49)
    assert sel.select([current, much], ctx).reason_code == "HYSTERESIS"  # sub DWELL_MIN = 3 min
    assert sel.select([current, much], sel.Context(t_now=50, last_switch_t=40)).decision == "REROUTE"
    urgent = sel.Context(t_now=50, last_switch_t=49, react=True, contact_min=5)
    assert sel.select([current, much], urgent).decision == "REROUTE"  # contact < 10 min: fără histerezis


def test_invalid_current_switches_immediately():
    current = alt("current", "CONTINUE", exposure_over_limit=True, exposure_min=4)
    other = alt("wait", "WAIT", extra_min=10)
    d = sel.select([current, other], sel.Context(t_now=1, last_switch_t=0))
    assert (d.decision, d.alternative_id) == ("WAIT", "wait")


def test_inbound_return_is_reported_as_reroute_with_phase():
    current = alt("current", "CONTINUE", exposure_over_limit=True)
    ret = alt("return", "RETURN")
    d = sel.select([current, ret], sel.Context(phase="INBOUND"))
    assert (d.decision, d.phase) == ("REROUTE", "INBOUND") and d.alternative_id == "return"


def test_emergency_relaxes_daylight_then_exposure_never_o2():
    current = alt("current", "CONTINUE", exposure_over_limit=True)
    late = alt("return", "RETURN", arrival_habitat_min=590)  # DAYLIGHT
    d = sel.select([current, late])
    assert (d.decision, d.alternative_id, d.relaxed) == ("EMERGENCY", "return", ["DAYLIGHT"])
    exposed = alt("return", "RETURN", arrival_habitat_min=590, exposure_over_limit=True)
    d = sel.select([current, exposed])
    assert d.decision == "EMERGENCY" and d.relaxed == ["DAYLIGHT", "HAZARD"] and "UNRECOVERABLE" not in d.flags
    no_o2 = alt("return", "RETURN", o2_end_pct=12)
    d = sel.select([current, no_o2])
    assert d.decision == "EMERGENCY" and "UNRECOVERABLE" in d.flags and d.alternative_id == "return"


def test_selection_is_deterministic():
    alts = lambda: [alt("current", "CONTINUE", risk=0.9, exposure_min=3), alt("detour_south", "REROUTE", o2_end_pct=55),
                    alt("detour_north", "REROUTE", o2_end_pct=55), alt("wait", "WAIT", extra_min=5)]
    assert len({sel.select(alts()).alternative_id for _ in range(10)}) == 1


def test_destination_first_valid_detour_beats_cheaper_return():
    """Destinația întâi (15.11): o ocolire validă care păstrează țintele câștigă în fața întoarcerii,
    chiar dacă întoarcerea are scor S mai bun (mai mult O₂ rămas); la fel traseul curent valid,
    chiar cu astronautul încă în amprenta pericolului. RETURN doar fără altă variantă validă."""
    ctx = sel.Context(in_hazard=True, react=True, contact_min=2)
    current = alt("current", "CONTINUE", o2_end_pct=60, risk=0.4)  # risc peste prag: se caută altceva
    detour = alt("detour_free", "REROUTE", o2_end_pct=55, extra_min=8)
    ret = alt("return", "RETURN", o2_end_pct=95, science_lost=["t"], science_lost_value=1.0)
    d = sel.select([current, detour, ret], ctx)
    assert (d.decision, d.alternative_id) == ("REROUTE", "detour_free")
    safe_current = alt("current", "CONTINUE", o2_end_pct=60)
    d = sel.select([safe_current, alt("wait", "WAIT", o2_end_pct=50, risk=0.9, crosses_hazard=True),
                    alt("return", "RETURN", o2_end_pct=95, science_lost=["t"], science_lost_value=1.0)], ctx)
    assert (d.decision, d.alternative_id) == ("CONTINUE", "current")
    blocked = alt("detour_free", "REROUTE", o2_end_pct=20)  # sub rezerva de O₂: invalidă
    d = sel.select([alt("current", "CONTINUE", risk=0.9, crosses_hazard=True), blocked, ret], ctx)
    assert d.decision == "RETURN"


def test_resume_safe_route_home_is_left_for_a_route_that_keeps_the_targets():
    """RESUME (15.11): drumul spre casă e sigur, dar pierde ținta; o variantă validă care o păstrează
    câștigă (fără ROUTE_OK și fără histerezis), ca astronautul să reia drumul după ce trece pericolul."""
    home = alt("current", "CONTINUE", o2_end_pct=90, science_lost=["t"], science_lost_value=1.0)
    resume = alt("detour_free", "REROUTE", o2_end_pct=60, extra_min=90)
    d = sel.select([home, resume], sel.Context())
    assert (d.decision, d.alternative_id) == ("REROUTE", "detour_free")
