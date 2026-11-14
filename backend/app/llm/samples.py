"""Situații tipice pentru testarea LLM-ului real (scripts/llm_bench.py și tests/llm/test_ollama_live.py).

Rezumatele trec prin `decision.choose` și `build_summary`, exact ca în motorul live.
"""

from app.core.decision import choose
from app.core.types import Alternative
from app.llm.summary import build_summary


def _alt(id, kind, **kw) -> Alternative:
    base = dict(path=[], extra_min=0, o2_end_pct=55, dose_msv=0.1, risk=0.1, arrival_habitat_min=220, sunset_min=420)
    return Alternative(id=id, kind=kind, **{**base, **kw})


def _current(**kw):
    return _alt("current", "CONTINUE", risk=0.8, crosses_hazard=True, **kw)


def _local_storm(eta, north_extra, north_o2, south_o2):
    return [
        _current(),
        _alt("detour_north", "REROUTE", extra_min=north_extra, o2_end_pct=north_o2, risk=0.12),
        _alt("detour_south", "REROUTE", extra_min=north_extra + 15, o2_end_pct=south_o2, risk=0.10),
        _alt("wait", "WAIT", extra_min=45, o2_end_pct=north_o2 - 2, risk=0.35),
        _alt("return", "RETURN", o2_end_pct=60, risk=0.05, science_lost_value=1.0, science_lost=["clay_delta"]),
    ], "local_storm", eta


def _regional(eta, o2_back):
    return [
        _current(),
        _alt("detour_north", "REROUTE", extra_min=30, o2_end_pct=40, risk=0.7, crosses_hazard=True),
        _alt("wait", "WAIT", extra_min=30, o2_end_pct=45, risk=0.9, crosses_hazard=True),
        _alt("return", "RETURN", o2_end_pct=o2_back, risk=0.2, science_lost_value=1.0, science_lost=["clay_delta"]),
    ], "regional_storm", eta


def _solar(o2_wait):
    return [
        _current(dose_msv=1.6),
        _alt("wait", "WAIT", extra_min=60, o2_end_pct=o2_wait, dose_msv=0.4, risk=0.15),
        _alt("return", "RETURN", o2_end_pct=62, dose_msv=0.9, risk=0.3, science_lost_value=0.7, science_lost=["carbonate_rim"]),
    ], "solar_particle_event", 0


def _suit_leak(o2_back):
    return [
        _alt("current", "CONTINUE", o2_end_pct=12, risk=0.6),
        _alt("return", "RETURN", o2_end_pct=o2_back, risk=0.1, science_lost_value=0.6, science_lost=["olivine_floor"]),
    ], "suit_leak", 0


def _emergency():
    return [
        _current(o2_end_pct=18),
        _alt("return", "RETURN", o2_end_pct=24, risk=0.2, science_lost_value=1.0),
    ], "regional_storm", 5


CASES = [
    ("local storm A", _local_storm(16, 25, 31, 22)),
    ("local storm B", _local_storm(9, 18, 38, 27)),
    ("local storm C", _local_storm(24, 32, 34, 25)),
    ("local storm D", _local_storm(12, 21, 41, 29)),
    ("local storm E", _local_storm(30, 40, 33, 21)),
    ("dust devil A", ([_current(), _alt("detour_north", "REROUTE", extra_min=4, o2_end_pct=52, risk=0.05),
                       _alt("return", "RETURN", o2_end_pct=65, risk=0.04, science_lost_value=1.0)], "dust_devil", 3)),
    ("dust devil B", ([_current(), _alt("detour_east", "REROUTE", extra_min=6, o2_end_pct=48, risk=0.06),
                       _alt("return", "RETURN", o2_end_pct=61, risk=0.04, science_lost_value=1.0)], "dust_devil", 2)),
    ("regional storm A", _regional(20, 58)),
    ("regional storm B", _regional(45, 47)),
    ("regional storm C", _regional(8, 66)),
    ("solar storm A", _solar(44)),
    ("solar storm B", _solar(37)),
    ("suit leak A", _suit_leak(41)),
    ("suit leak B", _suit_leak(33)),
    ("marsquake", ([_current(), _alt("detour_west", "REROUTE", extra_min=14, o2_end_pct=43, risk=0.15),
                    _alt("return", "RETURN", o2_end_pct=59, risk=0.05, science_lost_value=1.0)], "marsquake", 6)),
    ("emergency A", _emergency()),
    ("emergency B", ([_current(o2_end_pct=15), _alt("return", "RETURN", o2_end_pct=27, risk=0.3, arrival_habitat_min=400)],
                     "local_storm", 4)),
    ("late in the day", ([_current(), _alt("detour_north", "REROUTE", extra_min=35, o2_end_pct=36, risk=0.1, arrival_habitat_min=400),
                          _alt("return", "RETURN", o2_end_pct=50, risk=0.05, arrival_habitat_min=330, science_lost_value=1.0)], "local_storm", 11)),
    ("fatigue", ([_alt("current", "CONTINUE", o2_end_pct=29, risk=0.4),
                  _alt("return", "RETURN", o2_end_pct=44, risk=0.05, science_lost_value=0.5)], "fatigue", 0)),
    ("science preserved", _local_storm(14, 22, 45, 39)),
]


def situations() -> list[tuple[str, dict]]:
    """(nume, rezumat) pentru fiecare caz, ca în motorul live."""
    out = []
    for i, (name, (alternatives, hazard, eta)) in enumerate(CASES):
        decision = choose(alternatives)
        out.append((name, build_summary(decision, t_min=60 + 7 * i, hazard_kind=hazard, eta_hazard_min=eta)))
    return out
