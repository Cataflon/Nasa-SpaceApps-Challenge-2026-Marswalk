"""docs/sources.md rămâne sincron cu codul: fiecare DOI și link de date folosit în cod e listat acolo."""

import re

import fetch_stac as fs

ROOT = fs.ROOT
SOURCES = (ROOT / "docs" / "sources.md").read_text(encoding="utf-8")


def test_dois_in_code_are_listed():
    code = (ROOT / "backend" / "app" / "live" / "scenario.py").read_text(encoding="utf-8")
    dois = set(re.findall(r"doi:(10\.\d{4,}/[^\s,;)]+)", code))
    assert dois, "scenario.py ar trebui să citeze cel puțin un DOI"
    for d in dois:
        assert d in SOURCES, d


def test_data_urls_in_pipeline_are_listed():
    for url in (fs.WAYPOINTS_URL, fs.HELI_URL):
        assert url in SOURCES, url
    for spec in fs.COLLECTIONS.values():
        assert spec["collection"] in SOURCES, spec["collection"]


def test_every_row_has_a_status():
    rows = [line for line in SOURCES.splitlines() if line.startswith("| ") and not line.startswith("|---")]
    body = [r for r in rows if not r.startswith(("| Source", "| Paper", "| What"))]
    allowed = ("verified", "link verified", "to verify")
    for r in body:
        assert any(s in r.split("|")[-2] for s in allowed), r
