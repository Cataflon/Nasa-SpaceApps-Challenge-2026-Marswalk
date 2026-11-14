"""/api/site trimite hardware-ul NASA (artifacts) și traseul roverului (rover_traverse) din meta.json.

Adăugat de rolul 1 (cu acordul echipei); câmpurile sunt opționale în contract.
"""

import json

from fastapi.testclient import TestClient

from app.api.main import app
from app.config import CONTRACTS_DIR

TYPES = {"recovery_target", "landmark", "historical_hardware", "hazard_debris"}


def test_site_has_artifacts_and_traverse():
    body = TestClient(app).get("/api/site").json()
    assert "artifacts" in body and "rover_traverse" in body
    rows, cols = body["shape"]
    ids = [a["id"] for a in body["artifacts"]]
    assert len(ids) == len(set(ids))
    for a in body["artifacts"]:
        assert a["type"] in TYPES and a["name"] and a["note"]
        assert 0 <= a["row"] < rows and 0 <= a["col"] < cols
        assert a["caution_radius_m"] >= 0
    if body["rover_traverse"]:
        assert all(0 <= r < rows and 0 <= c < cols for r, c in body["rover_traverse"]["path"])


def test_site_has_eva_clock_and_earth_delay():
    body = TestClient(app).get("/api/site").json()
    assert body["eva_start_ltst_h"] == 8.0
    d = body["earth_delay_min"]
    assert d["one_way"] == 11.0 and d["round_trip"] > 2 * d["one_way"] and d["source"]


def test_site_mock_has_artifacts():
    mock = json.loads((CONTRACTS_DIR / "site.json").read_text(encoding="utf-8"))
    assert {a["id"] for a in mock["artifacts"]} >= {"three_forks_depot", "landing_site", "descent_stage"}
    assert "rover_traverse" in mock


def test_site_mock_clock_matches_scenario():
    """Fără sit generat (CI), /api/site întoarce mock-ul: ceasul și întârzierea trebuie să fie aceleași."""
    from app.live import scenario

    mock = json.loads((CONTRACTS_DIR / "site.json").read_text(encoding="utf-8"))
    assert mock["eva_start_ltst_h"] == scenario.EVA_START_LTST_H
    assert mock["earth_delay_min"] == {"one_way": scenario.EARTH_ONE_WAY_DELAY_MIN,
                                       "round_trip": scenario.EARTH_ROUND_TRIP_MIN,
                                       "source": scenario.EARTH_DELAY_SOURCE}
