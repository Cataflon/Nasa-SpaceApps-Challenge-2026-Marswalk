"""Replanificarea live (app/live/replan.py): cutremur pe traseul dus-întors, pe un sit plat mic."""

import sys
from pathlib import Path

import numpy as np

from app.core.hazards import from_contract
from app.core.validator import validate
from app.live import replan

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from grids import make_site  # noqa: E402

HABITAT, TARGET = (20, 2), (20, 77)


def quake_situation(center=(20, 40)):
    """Traseu habitat → țintă → habitat pe rândul 20 (dus și întors pe același culoar), cutremur
    de 120 m la mijloc. Exact cazul din F0: ocolirea veche refăcea doar dusul."""
    site = make_site(np.zeros((40, 80), dtype=np.float32), habitat=HABITAT,
                     targets=[{"id": "t", "name": "T", "kind": "clay", "row": TARGET[0], "col": TARGET[1],
                               "science_value": 10, "dwell_min": 10, "image": None}])
    out = [(20, c) for c in range(2, 78)]
    path = out + out[::-1][1:]
    quake = from_contract({"kind": "marsquake", "center": {"row": center[0], "col": center[1]}, "axes_m": [120, 120],
                           "intensity": 1.0}, site.cell_size_m, 0)
    return replan.Situation(site=site, position=path[0], current_path=path, stops=["t"], hazards=[quake],
                            t_min=0, o2_pct=100.0, dose_msv=0.0, sunset_min=1000.0)


def test_detours_avoid_the_quake_both_ways():
    alts = {a.id: a for a in validate(replan.candidates(quake_situation()))}
    assert "HAZARD" in alts["current"].violations
    detours = [a for a in alts.values() if a.kind == "REROUTE"]
    assert detours and all(a.valid for a in detours)
    for a in detours:  # traseu complet: ajunge la țintă și se întoarce acasă, fără să atingă zona
        assert TARGET in a.path and a.path[-1] == HABITAT and not a.science_lost and a.risk < 0.3


def test_same_input_same_candidates():
    first = [(a.id, a.path, round(a.risk, 6)) for a in replan.candidates(quake_situation())]
    assert first == [(a.id, a.path, round(a.risk, 6)) for a in replan.candidates(quake_situation())]


def test_destination_first_reroute_instead_of_return():
    d = replan.replan(quake_situation())
    assert (d.decision, d.reason_code) == ("REROUTE", "HAZARD_ON_ROUTE")
    chosen = next(a for a in d.alternatives if a.id == d.alternative_id)
    assert TARGET in chosen.path and chosen.path[-1] == HABITAT


def test_quake_on_target_returns_home():
    d = replan.replan(quake_situation(center=TARGET))
    assert (d.decision, d.alternative_id) == ("RETURN", "return")
