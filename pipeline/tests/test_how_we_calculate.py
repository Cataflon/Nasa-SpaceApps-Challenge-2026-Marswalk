"""docs/how-we-calculate.md listează fiecare constantă din codul care decide (rolurile 2 și 3).

Dacă cineva adaugă o constantă în core/ sau în motorul live fără să o documenteze, testul pică
și spune numele ei. Constantele pur tehnice (scalări, toleranțe numerice) sunt în IGNORED.
"""

import re

import fetch_stac as fs

ROOT = fs.ROOT
DOC = (ROOT / "docs" / "how-we-calculate.md").read_text(encoding="utf-8")

FILES = ["backend/app/core/budget.py", "backend/app/core/costmap.py", "backend/app/core/decision.py",
         "backend/app/core/hazards.py", "backend/app/core/daylight.py", "backend/app/core/planner.py",
         "backend/app/live/engine.py"]
IGNORED = {
    "TOBLER_MAX_KMH", "TOBLER_DECAY", "TOBLER_OFFSET",  # formula Tobler e scrisă întreagă
    "PRESETS",  # documentat pe componente: slope_k, w_hazard, w_radiation, w_science
    "RADIATION_EPS", "UNCERTAINTY_GROWTH_PER_MIN", "PROFILE_POINTS", "SQRT2",  # tehnice / nefolosite
    "O2_PCT_PER_MIN_WALK",  # derivată din WALK_WATTS
    "REEVAL_MIN", "HIT_HORIZON_MIN", "MAX_DURATION_MIN",  # cadența motorului, nu fizică
}
CONST = re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*(?::[^=]*)?=", re.M)


def constants():
    for rel in FILES:
        path = ROOT / rel
        if path.exists():
            for name in CONST.findall(path.read_text(encoding="utf-8")):
                if name not in IGNORED and not name.startswith("_"):
                    yield rel, name


def test_every_decision_constant_is_documented():
    missing = [f"{rel}: {name}" for rel, name in constants() if name not in DOC]
    assert not missing, "Lipsesc din docs/how-we-calculate.md:\n" + "\n".join(missing)


def test_status_badges_are_valid():
    rows = [r for r in DOC.splitlines() if r.startswith("| ") and not r.startswith(("| Quantity", "|---"))]
    assert len(rows) > 40
    for r in rows:
        status = r.rstrip().rstrip("|").split("|")[-1].strip()
        assert status in {"source", "to verify", "assumption"}, r
