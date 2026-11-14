"""Predicția și testul de conflict continuu (ARHITECTURA_RUTARE_V2 §4, corectează S1).

Pe fiecare segment de traseu [p_i → p_i+1], străbătut în [τ_i, τ_i+1] (din `eta_min`), în felii de
cel mult un tick, cu semiaxele înghețate la capătul feliei (conservator: cresc în timp):
    r(s) = r0 + w·s,  q(s) = S·R(−θ)·r(s) = q0 + z·s,  conflict ⇔ |q|² ≤ 1
adică (z·z)s² + 2(q0·z)s + (q0·q0 − 1) ≤ 0, rezolvat analitic. Nicio eșantionare pe pași de minute:
un vârtej mic și rapid nu mai poate trece printre eșantioane.

Funcțiile lucrează cu orice obiect care are `center_at(t)`, `axes_at(t)`, `theta_deg`, `active(t)`
(`HazardSpec`) sau, prin `hazard_track`, cu un `hazards.Hazard` din modelul vechi.
"""

import math
from dataclasses import dataclass

EPS = 1e-9
SLICE_MIN = 1.0  # o felie = cel mult un tick
# presupunere (C, §4): marginea de siguranță a amprentei (d_siguranță) și distanța de degajare a ocolirii.
SIDESTEP_MARGIN_M = 50.0
D_CLEAR_M = 50.0


@dataclass(frozen=True)
class Contact:
    """Un interval de conflict cu un pericol (timpi în minute de la începutul ieșirii)."""

    hazard_id: str
    t_in: float
    t_out: float
    exposure_min: float  # suma duratelor intervalelor de conflict
    depth: float  # min |q| pe traseu (0 = trece prin centru, 1 = atinge marginea)


class _Track:
    """Elipsa în timp: centru (y, x) m, semiaxe (a, b) m, unghi, interval de activitate."""

    def __init__(self, hid, center_at, axes_at, theta_deg, start=-math.inf, end=math.inf):
        self.id = hid
        self.center_at = center_at
        self.axes_at = axes_at
        self.theta = math.radians(theta_deg)
        self.start, self.end = start, end


def spec_track(spec, t_now: float = 0.0, margin_m: float = SIDESTEP_MARGIN_M, core: bool = False):
    """Pista unui HazardSpec: creștere aditivă cu plafon + δ⊥ plafonat la H_CONE + marjă (§4).

    δ⊥(Δt) = min(σ_rel·|v|·Δt, σ_rel·|v|·H_CONE), Δt = t − t_now, pe direcția perpendiculară pe mișcare.
    `core`: doar nucleul (semiaxele × core_fraction), fără marjă.
    """
    from app.core.hazard_spec import H_CONE_MIN

    frac = spec.effects.core_fraction if core else 1.0
    margin = 0.0 if core else margin_m

    def axes_at(t):
        a, b = spec.axes_at(t)
        vy, vx = spec.velocity_at(t)
        speed = math.hypot(vy, vx) * 60.0  # m/min
        delta = min(spec.sigma_rel * speed * max(0.0, t - t_now), spec.sigma_rel * speed * spec.horizon_cap_min
                    if spec.horizon_cap_min > 0 else spec.sigma_rel * speed * H_CONE_MIN)
        if speed > EPS and delta > 0:
            psi = math.atan2(vy, vx) - math.radians(spec.theta_deg)
            a, b = a + delta * abs(math.sin(psi)), b + delta * abs(math.cos(psi))
        return (a * frac + margin, b * frac + margin)

    return _Track(spec.id, spec.center_at, axes_at, spec.theta_deg, spec.start_min, spec.end_min)


def hazard_track(h, threshold: float, sigma_rel: float):
    """Pista unui `hazards.Hazard` (model vechi): zona cu intensitate ≥ prag, adică semiaxele × √(1 − prag/I),
    cu conul aditiv SIGMA_REL × |v| × Δ pe ambele semiaxe. None dacă intensitatea nu atinge pragul."""
    if h.intensity < threshold or h.intensity <= 0:
        return None
    scale = math.sqrt(max(0.0, 1.0 - threshold / h.intensity)) if threshold > 0 else 1.0
    scale = max(scale, 1e-6)  # prag = intensitatea maximă: zona e doar centrul (elipsă degenerată)
    speed = math.hypot(*h.velocity_ms) * 60.0
    cy0, cx0 = h.center_m
    vy, vx = h.velocity_ms

    def center_at(t):
        dt = (t - h.t0_min) * 60.0
        return (cy0 + vy * dt, cx0 + vx * dt)

    def axes_at(t):
        g = sigma_rel * speed * max(0.0, t - h.t0_min)
        return ((h.axes_m[0] + g) * scale, (h.axes_m[1] + g) * scale)

    if scale <= 0:
        return None
    return _Track(h.id, center_at, axes_at, h.angle_deg)


def _slice_interval(r0, w, a, b, theta, length):
    """Intervalul [s1, s2] ⊂ [0, length] cu |q(s)|² ≤ 1 și minimul lui |q|² pe felie."""
    ct, st = math.cos(theta), math.sin(theta)
    # (y, x) → coordonatele elipsei, ca în hazards._intensity: u = dx·cos + dy·sin, v = −dx·sin + dy·cos.
    q0 = ((r0[1] * ct + r0[0] * st) / a, (-r0[1] * st + r0[0] * ct) / b)
    z = ((w[1] * ct + w[0] * st) / a, (-w[1] * st + w[0] * ct) / b)
    A = z[0] * z[0] + z[1] * z[1]
    B = q0[0] * z[0] + q0[1] * z[1]
    C = q0[0] * q0[0] + q0[1] * q0[1] - 1.0
    if A < EPS or length <= EPS:
        depth2 = C + 1.0
        return ((0.0, length) if C <= EPS else None), depth2
    s_star = min(max(-B / A, 0.0), length)
    depth2 = A * s_star * s_star + 2 * B * s_star + C + 1.0
    disc = B * B - A * C
    if disc < 0:
        return None, depth2
    root = math.sqrt(disc)
    s1, s2 = (-B - root) / A, (-B + root) / A
    lo, hi = max(s1, 0.0), min(s2, length)
    return ((lo, hi) if hi >= lo - EPS else None), depth2


def track_intervals(points_m, eta, track) -> tuple[list[tuple[float, float]], float]:
    """Intervalele de conflict ale unei piste cu un traseu (puncte în metri, eta în minute) și min |q|."""
    out: list[tuple[float, float]] = []
    best = math.inf
    n = len(points_m)
    if n == 0:
        return out, best
    segments = [(i, i + 1) for i in range(n - 1)] or [(0, 0)]
    for i, j in segments:
        p0, p1 = points_m[i], points_m[j]
        t0, t1 = float(eta[i]), float(eta[j])
        if t1 < t0:
            t1 = t0
        span = t1 - t0
        if t1 < track.start - EPS or t0 > track.end + EPS:
            continue
        k = max(1, math.ceil(span / SLICE_MIN - EPS)) if span > EPS else 1
        for m in range(k):
            s0 = t0 + span * m / k
            s1 = t0 + span * (m + 1) / k
            lo_act, hi_act = max(s0, track.start), min(s1, track.end)
            if hi_act < lo_act - EPS:
                continue
            f0 = (s0 - t0) / span if span > EPS else 0.0
            f1 = (s1 - t0) / span if span > EPS else 0.0
            pa = (p0[0] + (p1[0] - p0[0]) * f0, p0[1] + (p1[1] - p0[1]) * f0)
            pb = (p0[0] + (p1[0] - p0[0]) * f1, p0[1] + (p1[1] - p0[1]) * f1)
            ca, cb = track.center_at(s0), track.center_at(s1)
            length = s1 - s0
            r0 = (pa[0] - ca[0], pa[1] - ca[1])
            if length > EPS:
                w = ((pb[0] - pa[0] - (cb[0] - ca[0])) / length, (pb[1] - pa[1] - (cb[1] - ca[1])) / length)
            else:
                w = (0.0, 0.0)
            a, b = track.axes_at(s1)  # înghețate la capătul feliei (cresc în timp: conservator)
            if a <= 0 or b <= 0:
                continue
            iv, depth2 = _slice_interval(r0, w, a, b, track.theta, length)
            best = min(best, depth2)
            if iv is None:
                continue
            lo, hi = max(s0 + iv[0], lo_act), min(s0 + iv[1], hi_act)
            if hi < lo - EPS:
                continue
            if out and lo <= out[-1][1] + EPS:
                out[-1] = (out[-1][0], max(out[-1][1], hi))
            else:
                out.append((lo, hi))
    return out, (math.sqrt(max(0.0, best)) if math.isfinite(best) else math.inf)


def to_metres(path, cell_size_m: float):
    return [((float(r) + 0.5) * cell_size_m, (float(c) + 0.5) * cell_size_m) for r, c in path]


def contacts(path, eta, specs, cell_size_m: float, t_now: float = 0.0, *, margin_m: float = SIDESTEP_MARGIN_M,
             core: bool = False, horizon_min: float | None = None) -> list[Contact]:
    """Contactele traseului cu pericolele geometrice (local, neignorate), sortate după (t_in, id).

    `horizon_min`: doar contactele care încep până la t_now + horizon_min (H_WATCH la watchdog).
    """
    pts = to_metres(path, cell_size_m)
    out = []
    for spec in sorted(specs, key=lambda s: s.id):
        if not spec.is_geometric():
            continue
        ivs, depth = track_intervals(pts, eta, spec_track(spec, t_now, margin_m, core))
        if horizon_min is not None:
            ivs = [iv for iv in ivs if iv[0] <= t_now + horizon_min + EPS]
        if ivs:
            out.append(Contact(spec.id, ivs[0][0], ivs[-1][1], sum(b - a for a, b in ivs), depth))
    return sorted(out, key=lambda c: (c.t_in, c.hazard_id))


def contains(spec, cell, t: float, cell_size_m: float, *, margin_m: float = 0.0, core: bool = False) -> bool:
    """Celula e în amprenta pericolului la t?"""
    if not spec.is_geometric() or not spec.active(t):
        return False
    ivs, _ = track_intervals(to_metres([cell], cell_size_m), [t], spec_track(spec, t, margin_m, core))
    return bool(ivs)


def extent_along(spec, t: float, direction_yx) -> float:
    """Întinderea elipsei (de la centru la margine) pe direcția dată (y, x)."""
    a, b = spec.axes_at(t)
    dy, dx = direction_yx
    norm = math.hypot(dy, dx)
    if norm < EPS:
        return max(a, b)
    th = math.radians(spec.theta_deg)
    u = (dx * math.cos(th) + dy * math.sin(th)) / norm
    v = (-dx * math.sin(th) + dy * math.cos(th)) / norm
    return 1.0 / math.sqrt((u / a) ** 2 + (v / b) ** 2)


def can_sidestep(spec, t_now: float, t_contact: float, route_dir_yx, v_astronaut_ms: float) -> bool:
    """Ocolirea e fezabilă? v_astronaut · t_contact ≥ a_perp(t_contact) + marjă + degajare (§4)."""
    perp = (-route_dir_yx[1], route_dir_yx[0])
    needed = extent_along(spec, t_contact, perp) + SIDESTEP_MARGIN_M + D_CLEAR_M
    return v_astronaut_ms * 60.0 * max(0.0, t_contact - t_now) >= needed - EPS
