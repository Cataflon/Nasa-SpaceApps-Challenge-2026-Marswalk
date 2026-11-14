import sys
from pathlib import Path

import pytest

# Scripturile din pipeline/ se importă direct (nu e pachet).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# CI-ul rulează `pytest pipeline/tests` din rădăcină, unde nu există pytest.ini. Înregistrăm
# aici marker-ul `slow` și sărim testele lente (rețea, rasterio) dacă nu sunt cerute cu `-m slow`.
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: test lent (> 5 s, rețea sau rasterio), rulat doar cu -m slow")


def pytest_collection_modifyitems(config, items):
    if "slow" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="test lent: rulează cu -m slow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
