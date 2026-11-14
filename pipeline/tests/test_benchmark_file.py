"""data/processed/jezero/benchmark.json: cifrele de pe slide-uri, în demo și în Survival Guide vin din el.

Nu rulează benchmark-ul (durează ~30 s și cere backendul); verifică doar că fișierul e coerent, că a fost
măsurat pe datele actuale ale sitului și că documentele de prezentare îl citează corect.
"""

import json
import re

import pytest

import fetch_stac as fs
from build_layers import OUT

PATH = OUT / "benchmark.json"


@pytest.fixture(scope="module")
def bench():
    if not PATH.exists():
        pytest.skip("benchmark.json nu e generat (python pipeline/run_benchmark.py)")
    return json.loads(PATH.read_text(encoding="utf-8"))


def pct(x: float) -> str:
    return f"{x:g}%"


def test_headline_matches_summaries(bench):
    h = bench["headline"]
    assert set(h) == {"copilot_safe_pct", "plan_safe_pct", "n_scenarios"}  # forma din README, „Noutăți” #5
    assert h["copilot_safe_pct"] == bench["copilot"]["safe_pct"] and h["plan_safe_pct"] == bench["plan_only"]["safe_pct"]
    assert sum(bench["storm_kinds"].values()) == h["n_scenarios"]


def test_measured_on_current_site_data(bench):
    meta = json.loads((OUT / "meta.json").read_text(encoding="utf-8"))
    assert bench["site_fingerprint"] == meta["fingerprint"], "situl s-a schimbat: rulează pipeline/run_benchmark.py"


def test_presentation_docs_quote_it(bench):
    h, c, p = bench["headline"], bench["copilot"], bench["plan_only"]
    docs = {name: (fs.ROOT / "docs" / name).read_text(encoding="utf-8") for name in ("slides.md", "demo.md", "survival-guide.md")}
    flat = {k: re.sub(r"\s+", " ", v) for k, v in docs.items()}
    assert f"home safely in {pct(h['copilot_safe_pct'])} of storms. The fixed plan: {pct(h['plan_safe_pct'])}" in flat["slides.md"]
    assert f"| **Home safely** | **{pct(h['plan_safe_pct'])}** | **{pct(h['copilot_safe_pct'])}** |" in flat["slides.md"]
    assert f"| Samples collected | {pct(p['science_pct'])} | {pct(c['science_pct'])} |" in flat["slides.md"]
    assert f"rescued {bench['rescued_by_copilot']} walks" in flat["slides.md"]
    assert f"copilot {pct(h['copilot_safe_pct'])} safe, fixed plan {pct(h['plan_safe_pct'])}" in flat["demo.md"]
    assert f"({pct(c['science_pct'])} vs {pct(p['science_pct'])})" in flat["survival-guide.md"]
    assert f"({pct(h['copilot_safe_pct'])} vs {pct(h['plan_safe_pct'])})" in flat["survival-guide.md"]
