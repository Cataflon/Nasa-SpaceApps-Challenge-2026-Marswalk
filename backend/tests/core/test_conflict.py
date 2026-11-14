"""F1: testul de conflict continuu (ARHITECTURA_RUTARE_V2 §4), comparat cu o eșantionare foarte fină."""

import math

import numpy as np
import pytest

from app.core import conflict as cf
from app.core import hazard_spec as hs
from app.core import hazards as hz

CELL = 20.0
SEED = 42


def spec(center_rc, axes, v=(0.0, 0.0), *, t0=0.0, alpha=0.0, sigma=0.0, kind="custom", theta=0.0, hid="h"):
    res = hs.normalize({"id": hid, "kind": kind, "shape": {"center": {"row": center_rc[0], "col": center_rc[1]},
                                                           "axes_m": list(axes), "theta_deg": theta},
                        "motion": [{"from_min": t0, "velocity_ms": list(v)}],
                        "growth": {"alpha_m_per_min": alpha, "cap_axes_m": [axes[0] + 1e6, axes[1] + 1e6]},
                        "uncertainty": {"sigma_rel": sigma, "horizon_cap_min": 15}},
                       cell_size_m=CELL, t_now=t0)
    assert res.ok, res.error
    return res.spec


def sampled_exposure(path, eta, s, step_s=1.0, margin=cf.SIDESTEP_MARGIN_M):
    """Expunerea eșantionată la pas de 1 s (referința lentă), cu aceeași pistă (aceleași semiaxe)."""
    track = cf.spec_track(s, 0.0, margin)
    pts = cf.to_metres(path, CELL)
    inside, total, t_first = 0, 0, None
    for i in range(len(path) - 1):
        t0, t1 = eta[i], eta[i + 1]
        n = max(1, int(round((t1 - t0) * 60 / step_s)))
        for k in range(n):
            t = t0 + (t1 - t0) * k / n
            f = k / n
            y = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f
            x = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f
            cy, cx = track.center_at(t)
            a, b = track.axes_at(t)
            th = track.theta
            u = (x - cx) * math.cos(th) + (y - cy) * math.sin(th)
            w = -(x - cx) * math.sin(th) + (y - cy) * math.cos(th)
            if (u / a) ** 2 + (w / b) ** 2 <= 1.0:
                inside += 1
                t_first = t if t_first is None else t_first
            total += 1
    return inside * step_s / 60.0, t_first


def test_continuous_matches_fine_sampling_on_60_cases():
    rng = np.random.default_rng(SEED)
    checked = 0
    for case in range(60):
        n = int(rng.integers(5, 25))
        r0, c0 = rng.uniform(20, 80, 2)
        heading = rng.uniform(0, 2 * math.pi)
        path = [(int(round(r0 + i * math.sin(heading) * 2)), int(round(c0 + i * math.cos(heading) * 2))) for i in range(n)]
        step = float(rng.uniform(0.3, 2.0))
        eta = [i * step for i in range(n)]
        mid = path[n // 2]
        s = spec((mid[0] + rng.uniform(-6, 6), mid[1] + rng.uniform(-6, 6)), (rng.uniform(40, 200), rng.uniform(40, 200)),
                 v=tuple(rng.uniform(-3, 3, 2)), alpha=float(rng.uniform(0, 5)), sigma=float(rng.uniform(0, 0.3)),
                 theta=float(rng.uniform(0, 180)))
        found = cf.contacts(path, eta, [s], CELL)
        exp_cont = found[0].exposure_min if found else 0.0
        exp_samp, t_first = sampled_exposure(path, eta, s)
        # Continuu ≥ eșantionat (semiaxele sunt înghețate la capătul feliei: conservator), diferență < 1 tick.
        # Toleranța referinței eșantionate: ≤ 1 s de rotunjire pe segment + un eșantion la intrare și la ieșire.
        tol = (len(path) + 2) / 60.0
        assert exp_cont >= exp_samp - tol, (case, exp_cont, exp_samp)
        assert exp_cont - exp_samp < 1.0, (case, exp_cont, exp_samp)
        if t_first is not None:
            assert found and found[0].t_in <= t_first + 1.0 / 60.0, case
            checked += 1
    assert checked >= 20  # destule cazuri cu contact real


def test_small_fast_vortex_between_5_min_samples_is_detected():
    """Vârtej de 60 m care traversează traseul în ~1 min: eșantionarea la 5 min l-ar rata."""
    path = [(50, c) for c in range(0, 61)]  # spre est, 1 celulă / 0,5 min
    eta = [0.5 * i for i in range(61)]
    # La t = 12 min astronautul e la col 24; vârtejul trece pe col 24 de la nord la sud cu 10 m/s.
    s = spec((50 - 12 * 60 * 10 / CELL, 24), (60, 60), v=(10.0, 0.0), kind="dust_devil")
    sampled_5min = [t for t in range(0, 31, 5)
                    if cf.contains(s, path[min(60, int(t / 0.5))], float(t), CELL, margin_m=0.0)]
    assert sampled_5min == []  # nu e văzut la eșantioanele de 5 min
    found = cf.contacts(path, eta, [s], CELL, margin_m=0.0)
    assert found and 11.0 < found[0].t_in < 12.5 and found[0].exposure_min < 1.0


def test_hazard_passing_behind_the_astronaut_is_not_a_conflict():
    """SC-17: pericolul trece peste traseu înainte ca astronautul să ajungă acolo (celulele sunt deja libere)."""
    path = [(50, c) for c in range(0, 41)]
    eta = [float(i) for i in range(41)]  # ajunge la col 30 la minutul 30
    # Pericolul traversează col 30 de la nord la sud, între minutele ~0 și ~6, apoi pleacă.
    s = spec((50 - 4000 / CELL / 2, 30), (100, 100), v=(5.0, 0.0))
    assert cf.contacts(path, eta, [s], CELL) == []
    # Același pericol, dar astronautul ajunge acolo exact când trece: conflict.
    fast = [float(i) * 0.1 for i in range(41)]
    s2 = spec((50, 2), (100, 100), v=(0.0, 0.0))
    assert cf.contacts(path, fast, [s2], CELL)


def test_waiting_segment_uses_the_same_test():
    """Așteptare (viteză 0) într-un loc peste care trece pericolul."""
    s = spec((50, 10), (100, 100), v=(0.0, 1.0))  # spre est, 60 m/min
    path, eta = [(50, 20), (50, 20)], [0.0, 10.0]
    found = cf.contacts(path, eta, [s], CELL, margin_m=0.0)
    assert found and found[0].t_in < found[0].t_out <= 10.0 + 1e-9


def test_growth_cap_and_perpendicular_uncertainty_are_capped():
    s = spec((50, 50), (100, 100), v=(0.0, 2.0), alpha=10.0, sigma=0.5)
    s = hs.normalize({"id": "g", "kind": "custom", "shape": {"center": {"row": 50, "col": 50}, "axes_m": [100, 100]},
                      "motion": [{"from_min": 0, "velocity_ms": [0, 2.0]}],
                      "growth": {"alpha_m_per_min": 10}, "uncertainty": {"sigma_rel": 0.5, "horizon_cap_min": 15}},
                     cell_size_m=CELL).spec
    track = cf.spec_track(s, 0.0, margin_m=0.0)
    a15, b15 = track.axes_at(15)
    a90, b90 = track.axes_at(90)
    assert (a15, b15) == pytest.approx((a90, b90))  # creștere și con plafonate la H_CONE
    # δ⊥ = σ·|v|·H_CONE = 0,5 · 120 m/min · 15 = 900 m, pe semiaxa perpendiculară pe mișcare (b, mișcare spre est).
    assert b90 - a90 == pytest.approx(900.0)


def test_depth_and_inactive_hazard():
    s = spec((50, 20), (100, 100))
    path, eta = [(50, c) for c in range(0, 41)], [float(i) for i in range(41)]
    c = cf.contacts(path, eta, [s], CELL, margin_m=0.0)[0]
    assert c.depth == pytest.approx(0.0, abs=0.11)  # trece prin centru
    later = hs.normalize({"id": "late", "kind": "custom", "shape": {"center": {"row": 50, "col": 20}, "axes_m": [100, 100]},
                          "lifetime": {"start_min": 100, "duration_min": 10}}, cell_size_m=CELL).spec
    assert cf.contacts(path, eta, [later], CELL) == []  # încă inactiv când trece astronautul
    ignored = spec((50, 20), (10, 10))
    assert ignored.ignored and cf.contacts(path, eta, [ignored], CELL) == []


def test_can_sidestep():
    s = spec((50, 50), (300, 300))
    route_dir = (0.0, 1.0)  # spre est
    v = 0.84  # m/s, Tobler × SUIT_FACTOR pe plat
    # nevoie: 300 + 50 + 50 = 400 m → la 50 m/min, cel puțin 8 min până la contact
    assert not cf.can_sidestep(s, 0.0, 5.0, route_dir, v)
    assert cf.can_sidestep(s, 0.0, 10.0, route_dir, v)


def test_route_hit_continuous_finds_fast_crossing_missed_by_points():
    """route_hit (semnătură neschimbată) folosește acum testul continuu."""
    h = hz.Hazard("dd", "dust_devil", ((40 + 0.5) * CELL, (24 + 0.5) * CELL), (60.0, 60.0), 0.0, 0.9, (10.0 / 3, 0.0), 0.0)
    # Pericolul ajunge pe rândul 50 (col 24) la ~minutul 1; traseul are puncte doar la col 0 și col 48.
    path, eta = [(50, 0), (50, 48)], [0.0, 2.0]
    old_hazards_sigma = hz.SIGMA_REL
    try:
        hz.SIGMA_REL = 0.0
        hit, t = hz.route_hit(path, eta, [h], CELL)
        assert hit and 0.5 < t < 1.5
        assert hz.route_risk(path, eta, [h], CELL) < hz.HIT_THRESHOLD  # pe puncte nu se vede
    finally:
        hz.SIGMA_REL = old_hazards_sigma
