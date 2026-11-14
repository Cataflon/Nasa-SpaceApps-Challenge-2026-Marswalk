"""docs/survival-guide.md: fiecare prag e cel din cod (nu inventat aici), iar textul merge în
mini-renderer-ul rolului 4 (titluri, liste „- ”, **bold**, `cod`, tabele, linii orizontale).

Constantele se citesc din sursă cu regex (CI-ul pipeline nu instalează backendul).
"""

import json
import re

import fetch_stac as fs

ROOT = fs.ROOT
GUIDE = (ROOT / "docs" / "survival-guide.md").read_text(encoding="utf-8")
FLAT = re.sub(r"\s+", " ", GUIDE)


def const(rel: str, pattern: str) -> float:
    m = re.search(pattern, (ROOT / rel).read_text(encoding="utf-8"), re.M)
    assert m, f"{pattern} lipsește din {rel}"
    return float(m.group(1))


def num(x: float) -> str:
    return f"{x:g}"


def test_limits_match_code():
    reserve = const("backend/app/core/types.py", r"o2_reserve_pct: float = ([\d.]+)")
    margin = const("backend/app/core/types.py", r"sunset_margin_min: float = ([\d.]+)")
    dose = const("backend/app/core/types.py", r"max_dose_msv: float = ([\d.]+)")
    slope = json.loads((ROOT / "data" / "processed" / "jezero" / "meta.json").read_text(encoding="utf-8"))["max_slope_deg"]
    assert f"**at least {num(reserve)}%** left" in FLAT
    assert f"**{num(margin)} min before sunset**" in FLAT
    assert f"**{num(slope)}°**" in FLAT
    assert f"**{num(dose)} mSv** at most" in FLAT
    assert f"less than {num(reserve)}%" in FLAT


def test_earth_delay_matches_scenario():
    one_way = const("backend/app/live/scenario.py", r"^EARTH_ONE_WAY_DELAY_MIN = ([\d.]+)")
    react = const("backend/app/live/scenario.py", r"^MISSION_CONTROL_REACTION_MIN = ([\d.]+)")
    assert f"about **{num(2 * one_way + react)} min**" in FLAT
    assert f"{num(one_way)} min each way + {num(react)} min to react" in FLAT


def test_events_match_code():
    spe = re.search(r'"dose_rate_multiplier": ([\d.]+).*?"rise_min": ([\d.]+).*?"decay_min": ([\d.]+)',
                    (ROOT / "backend/app/live/scenario.py").read_text(encoding="utf-8"), re.S)
    mult, rise, decay = (float(g) for g in spe.groups())
    assert f"up to about {num(mult)} times normal" in FLAT
    assert rise == 120 and "over about 2 hours" in FLAT
    assert decay == 2880 and "more than two days" in FLAT
    leak = const("backend/app/live/engine.py", r"^SUIT_LEAK_PCT_PER_MIN = ([\d.]+)")
    speed = const("backend/app/live/engine.py", r"^FATIGUE_SPEED_FACTOR = ([\d.]+)")
    o2 = const("backend/app/live/engine.py", r"^FATIGUE_O2_FACTOR = ([\d.]+)")
    assert f"about {num(leak)}% per minute" in FLAT
    assert f"{num(round(speed * 100))}% of your speed and {num(round(o2 * 100))}% of your oxygen use" in FLAT


def test_every_situation_has_a_section():
    for title in ["Dust devil", "Storm front", "Regional dust storm", "Solar storm", "Suit leak", "Fatigue",
                  "Marsquake", "Loss of contact"]:
        assert re.search(rf"^## {title}", GUIDE, re.M), title


def test_renders_with_the_frontend_mini_renderer():
    """Fără liste numerotate, link-uri, cursive sau HTML: renderer-ul rolului 4 nu le cunoaște."""
    assert not re.search(r"^\s*\d+\. ", GUIDE, re.M)
    assert "](" not in GUIDE and "<" not in GUIDE
    assert not re.search(r"(?<![*\w])\*[^*\s][^*]*\*(?!\*)", GUIDE)
    # o pagină A4 de reguli: scurt
    assert len(GUIDE.split()) < 750
