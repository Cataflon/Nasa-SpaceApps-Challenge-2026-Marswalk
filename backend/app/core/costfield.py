"""Câmpurile de cost dinamice (ARHITECTURA_RUTARE_V2 §5): timpul estimat t_est(v) și C_temp.

- `t_est_grid`: Dijkstra înainte, din poziția curentă, cu costul = minute de mers (cu multiplicatorul
  de viteză al efectelor active). Corectează S3: pericolul se evaluează în fiecare celulă la momentul
  la care ar ajunge astronautul acolo, nu la momentul de acum.
- `temp_cost`: C_temp = C_static + Σ Φ_k, cu nucleu M_CORE, halou M_HALO·(1 − d)², suma plafonată la
  M_MAX. Un pericol care conține deja astronautul rămâne finit și crește spre centru (gradient de
  ieșire); +∞ doar pentru `block = all` care nu conține startul.
"""

import math

import numpy as np

from app.core.budget import minutes_grid
from app.core.conflict import SIDESTEP_MARGIN_M, contains
from app.core.costmap import static_cost
from app.core.planner import site_cache
from app.core.routing import N_MAX, reverse_dijkstra_multi
from app.core.site_data import Site

# presupunere (C, §5, §11): penalizările pericolelor în cost.
M_CORE = 1000.0
M_HALO = 200.0
M_MAX = 5000.0
# presupunere (C): t_est pe blocuri de 5 × 5 celule (100 m). Specificația cere doar o aproximare
# (timpul real se verifică în validator); pe 500 × 500 un Dijkstra complet durează ~0,7 s, pe blocuri ~30 ms.
T_EST_DOWNSAMPLE = 5
# presupunere (C): dincolo de atâtea minute de acum, pericolul se evaluează la acest orizont (celulele
# foarte îndepărtate nu mai schimbă decizia, iar dreptunghiul de calcul rămâne mic).
COST_HORIZON_MIN = 240.0
SWEEP_STEP_MIN = 10.0  # pasul cu care se estimează dreptunghiul măturat de pericol


def t_est_grid(site: Site, position, t_now: float, speed_mult: float = 1.0,
               downsample: int = T_EST_DOWNSAMPLE, max_expansions: int = N_MAX) -> np.ndarray:
    """Minutul estimat de sosire în fiecare celulă (t_now + timpul de mers din `position`); inf = inaccesibil.

    Pe blocuri f × f: timpul unui bloc = f × media minutelor celulelor permise (inf dacă niciuna nu e
    permisă); rezultatul se extinde înapoi pe grila fină. Determinist, fără excepții.
    """
    speed_mult = max(float(speed_mult), 1e-3)
    minutes = site_cache(site, f"minutes:{speed_mult:.6f}", lambda: minutes_grid(site, fatigue=speed_mult))
    rows, cols = minutes.shape
    f = max(1, int(downsample))
    hc, wc = -(-rows // f), -(-cols // f)
    padded = np.full((hc * f, wc * f), np.inf)
    padded[:rows, :cols] = minutes
    blocks = padded.reshape(hc, f, wc, f)
    finite = np.isfinite(blocks)
    count = finite.sum(axis=(1, 3))
    total = np.where(finite, blocks, 0.0).sum(axis=(1, 3))
    coarse = np.where(count > 0, f * total / np.maximum(count, 1), np.inf)
    r = int(min(max(round(float(position[0])), 0), rows - 1)) // f
    c = int(min(max(round(float(position[1])), 0), cols - 1)) // f
    if not np.isfinite(coarse[r, c]):
        coarse[r, c] = float(np.nanmax(np.where(np.isfinite(coarse), coarse, np.nan))) if np.isfinite(coarse).any() else 1.0
    times, _ = reverse_dijkstra_multi(coarse, [(r, c)], max_expansions)
    fine = np.repeat(np.repeat(times, f, axis=0), f, axis=1)[:rows, :cols]
    return t_now + fine


def _centers(spec, t: np.ndarray):
    """Centrul (y, x) pe tablouri de timpi, pe segmentele de mișcare (vectorizat)."""
    cy = np.full(t.shape, spec.center_m[0], dtype=np.float64)
    cx = np.full(t.shape, spec.center_m[1], dtype=np.float64)
    bounds = [s.from_min for s in spec.motion] + [math.inf]
    for i, seg in enumerate(spec.motion):
        lo, hi = seg.from_min, bounds[i + 1]
        # timp petrecut în segment între t0 și t (semn negativ dacă t < t0)
        fwd = np.clip(np.minimum(t, hi) - max(lo, spec.t0_min), 0.0, None) if hi > spec.t0_min else 0.0
        back = np.clip(min(hi, spec.t0_min) - np.maximum(t, lo), 0.0, None) if lo < spec.t0_min else 0.0
        dt = (fwd - back) * 60.0
        cy += seg.velocity_ms[0] * dt
        cx += seg.velocity_ms[1] * dt
    return cy, cx


def _axes(spec, t: np.ndarray, t_now: float):
    """Semiaxele pe tablouri de timpi: creștere cu plafon + δ⊥ plafonat (ca `conflict.spec_track`)."""
    dt = np.maximum(0.0, t - spec.t0_min)
    a = np.minimum(spec.axes_m[0] + spec.alpha_m_per_min * dt, max(spec.cap_axes_m[0], spec.axes_m[0]))
    b = np.minimum(spec.axes_m[1] + spec.alpha_m_per_min * dt, max(spec.cap_axes_m[1], spec.axes_m[1]))
    vy, vx = spec.velocity_at(t_now)
    speed = math.hypot(vy, vx) * 60.0
    if speed > 0 and spec.sigma_rel > 0:
        delta = np.minimum(spec.sigma_rel * speed * np.maximum(0.0, t - t_now), spec.sigma_rel * speed * spec.horizon_cap_min)
        psi = math.atan2(vy, vx) - math.radians(spec.theta_deg)
        a = a + delta * abs(math.sin(psi))
        b = b + delta * abs(math.cos(psi))
    return a, b


def _bbox(spec, t_now: float, horizon: float, shape, cell: float):
    """Dreptunghiul de celule care poate fi atins de amprentă pe [t_now, horizon] (sau None)."""
    ts = np.arange(max(t_now, spec.start_min), min(horizon, spec.end_min) + SWEEP_STEP_MIN, SWEEP_STEP_MIN)
    if ts.size == 0:
        return None
    cy, cx = _centers(spec, ts)
    a, b = _axes(spec, ts, t_now)
    reach = float(np.max(np.maximum(a, b))) + SIDESTEP_MARGIN_M
    reach += max(abs(v) for seg in spec.motion for v in seg.velocity_ms) * 60.0 * SWEEP_STEP_MIN if spec.motion else 0.0
    rows, cols = shape
    r0 = max(0, int(math.floor((float(cy.min()) - reach) / cell)))
    r1 = min(rows, int(math.ceil((float(cy.max()) + reach) / cell)) + 1)
    c0 = max(0, int(math.floor((float(cx.min()) - reach) / cell)))
    c1 = min(cols, int(math.ceil((float(cx.max()) + reach) / cell)) + 1)
    if r0 >= r1 or c0 >= c1:
        return None
    return r0, r1, c0, c1


def hazard_penalty(site: Site, spec, t_now: float, t_est: np.ndarray, start=None) -> tuple[np.ndarray, np.ndarray]:
    """(Φ finit, mască +∞) pentru un pericol, evaluat în fiecare celulă la t_est(v)."""
    shape = site.shape
    cell = site.cell_size_m
    phi = np.zeros(shape)
    block_inf = np.zeros(shape, dtype=bool)
    if not spec.is_geometric() or spec.effects.block == "none" and not spec.effects.soft_halo:
        return phi, block_inf
    horizon = t_now + COST_HORIZON_MIN
    box = _bbox(spec, t_now, horizon, shape, cell)
    if box is None:
        return phi, block_inf
    r0, r1, c0, c1 = box
    t = np.where(np.isfinite(t_est[r0:r1, c0:c1]), t_est[r0:r1, c0:c1], t_now)
    t = np.clip(t, t_now, horizon)
    active = (t >= spec.start_min - 1e-9) & (t <= spec.end_min + 1e-9)
    cy, cx = _centers(spec, t)
    a, b = _axes(spec, t, t_now)
    a_out, b_out = a + SIDESTEP_MARGIN_M, b + SIDESTEP_MARGIN_M
    yy = (np.arange(r0, r1)[:, None] + 0.5) * cell - cy
    xx = (np.arange(c0, c1)[None, :] + 0.5) * cell - cx
    th = math.radians(spec.theta_deg)
    u = xx * math.cos(th) + yy * math.sin(th)
    v = -xx * math.sin(th) + yy * math.cos(th)
    d_out = np.sqrt((u / a_out) ** 2 + (v / b_out) ** 2)
    frac = max(spec.effects.core_fraction, 1e-6)
    d_core = np.sqrt((u / (a * frac)) ** 2 + (v / (b * frac)) ** 2)
    in_core = active & (d_core <= 1.0) & (spec.effects.block != "none")
    in_halo = active & (d_out <= 1.0) & ~in_core & spec.effects.soft_halo
    if spec.effects.block_slope_deg is not None:  # zonă statică: blocate doar pantele mari
        steep = site.layers["slope"][r0:r1, c0:c1] > spec.effects.block_slope_deg
        in_halo |= in_core & ~steep & spec.effects.soft_halo
        in_core &= steep
    holds_start = start is not None and contains(spec, start, t_now, cell)
    local = np.zeros(t.shape)
    local[in_halo] = M_HALO * (1.0 - np.clip(d_out[in_halo], 0.0, 1.0)) ** 2
    if holds_start:
        # Start în pericol: finit, crește spre centru → gradient de ieșire (nu există +∞).
        local[in_core] = M_CORE * (1.0 - np.clip(d_out[in_core], 0.0, 1.0)) + M_HALO
    elif spec.effects.block == "all":
        block_inf[r0:r1, c0:c1] = in_core
    else:
        local[in_core] = M_CORE
    phi[r0:r1, c0:c1] = local
    return phi, block_inf


def temp_cost(site: Site, preset: str, specs, t_now: float, t_est: np.ndarray, start=None) -> np.ndarray:
    """C_temp = C_static + min(Σ Φ_k, M_MAX); +∞ unde un pericol `block = all` (care nu conține startul)
    acoperă nucleul. Celula de start rămâne finită (§8.2: astronaut pe celulă interzisă)."""
    base = static_cost(site, preset)
    total = np.zeros(site.shape)
    blocked = np.zeros(site.shape, dtype=bool)
    for spec in sorted(specs, key=lambda s: s.id):
        phi, inf_mask = hazard_penalty(site, spec, t_now, t_est, start)
        total += phi
        blocked |= inf_mask
    cost = base + np.minimum(total, M_MAX)
    cost[blocked] = np.inf
    if start is not None:
        r, c = int(start[0]), int(start[1])
        if 0 <= r < cost.shape[0] and 0 <= c < cost.shape[1] and not np.isfinite(cost[r, c]):
            finite = base[np.isfinite(base)]
            cost[r, c] = float(finite.max()) if finite.size else 1.0
    return cost
