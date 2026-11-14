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


def test_site_mock_has_artifacts():
    mock = json.loads((CONTRACTS_DIR / "site.json").read_text(encoding="utf-8"))
    assert {a["id"] for a in mock["artifacts"]} >= {"three_forks_depot", "landing_site", "descent_stage"}
    assert "rover_traverse" in mock
