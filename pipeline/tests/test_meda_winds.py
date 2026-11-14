"""Transcrierea tabelelor MEDA (Viúdez-Moreiras et al. 2022) e verificată pe ea însăși:
media și percentilele calculate din (c, k) din Tabelul 1 trebuie să dea Tabelul 2."""

import json

import pytest

import meda_winds as mw
from build_layers import OUT

ROWS = list(mw.WEIBULL_BY_TIMESLOT.items()) + [("total", mw.WEIBULL_TOTAL)]


@pytest.mark.parametrize("name,s", ROWS, ids=[r[0] for r in ROWS])
def test_table1_reproduces_table2(name, s):
    c, k = s["c_ms"], s["k"]
    assert mw.weibull_mean(c, k) == pytest.approx(s["table2_mean_ms"], abs=0.02)
    assert mw.weibull_quantile(c, k, 0.95) == pytest.approx(s["p95_ms"], abs=0.03)
    assert mw.weibull_quantile(c, k, 0.99) == pytest.approx(s["p99_ms"], abs=0.03)


def test_timeslots_cover_the_sol():
    hours = sorted(h for s in mw.WEIBULL_BY_TIMESLOT.values() for h in range(*s["ltst_h"]))
    assert hours == list(range(24))


def test_committed_wind_stats_is_up_to_date():
    path = OUT / "wind_stats.json"
    if not path.exists():
        pytest.skip("wind_stats.json nu e generat")
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(json.dumps(mw.build()))
