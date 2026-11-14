"""Modelul unificat de hazard (ARHITECTURA_RUTARE_V2 §2): calamități parametrizabile, cu revizii.

Orice pericol, din scenariu sau injectat de utilizator, e un `HazardSpec`. Tipurile din cercetare
(`docs/hazards-research.md`) sunt doar seturi implicite de parametri (`CLASS_DEFAULTS`); `custom`
poate combina orice. Convenții ca în `hazards.Hazard`: metri de la colțul NV, (y spre sud, x spre
est), `theta_deg` = direcția semiaxei a, de la est, în sensul acelor de ceasornic pe hartă.

Determinist: nicio funcție nu folosește ceasul real sau numere aleatoare; specificațiile invalide
întorc un cod de eroare stabil, nu o excepție.
"""

import math
from dataclasses import dataclass, field, replace

from app.core import hazards as hz

# --- Parametri (ARHITECTURA_RUTARE_V2 §11) ---
# B: registrul §3 (vânt măsurat în celulele de furtună 20-45 m/s); peste atât, viteza e plafonată.
V_HAZARD_MAX_MS = 40.0
# presupunere (C, §2.1): vârtejurile sub 30 m rază „nu contează” pentru un astronaut în costum.
IGNORE_RADIUS_M = 30.0
# presupunere (C): peste 60 % din celule acoperite, pericolul nu are „ieșire”: e tratat ca global.
GLOBAL_COVERAGE = 0.6
# presupunere (C, §3): orizonturile; H_WATCH doar avertizează, H_REACT declanșează replanificarea,
# H_CONE plafonează creșterea conului de incertitudine.
H_WATCH_MIN = 90.0
H_REACT_MIN = 30.0
H_CONE_MIN = 15.0
# presupunere (C): eșantioanele în timp pentru testul de acoperire globală (din 15 în 15 min pe H_WATCH)
COVERAGE_STEP_MIN = 15.0
COVERAGE_SAMPLES = 40  # grilă 40 × 40 de puncte pentru fracția de hartă acoperită (aproximare analitică)

SCOPES = ("local", "global", "point")
BLOCKS = ("none", "core", "all")
HUB_EFFECTS = ("none", "degraded", "unusable")
OPS = ("add", "update", "remove")

# Codurile de eroare și avertismentele (stabile, apar în ieșire).
ERR_NAN = "NAN_VALUE"
ERR_SHAPE = "BAD_SHAPE"
ERR_CENTER = "MISSING_CENTER"
ERR_OP = "BAD_OP"
ERR_UNKNOWN_ID = "UNKNOWN_ID"
WARN_SPEED = "SPEED_CAPPED"
WARN_KIND = "UNKNOWN_KIND_AS_CUSTOM"
WARN_UPDATE_AS_ADD = "UPDATE_ON_MISSING_ID"
WARN_ADD_AS_UPDATE = "ADD_ON_EXISTING_ID"
WARN_GLOBAL = "COVERAGE_GLOBAL"
WARN_IGNORED = "SMALL_IGNORED"
WARN_PAST = "EVENT_IN_PAST"


@dataclass(frozen=True)
class Effects:
    """Efectele unui pericol (§2). Multiplicatorii se aplică în interior (local) sau peste tot (global)."""

    block: str = "core"  # none | core | all
    core_fraction: float = 0.5  # nucleul = elipsa cu semiaxele × core_fraction
    soft_halo: bool = True  # penalizare gradată între nucleu și marginea elipsei
    speed_mult: float = 1.0
    o2_mult: float = 1.0
    o2_add_pct_min: float = 0.0
    dose_mult: float = 1.0
    daylight_shift_min: float = 0.0  # negativ = apus mai devreme
    exposure_limit_min: float = 0.0  # cât timp în interior e tolerat (0 = deloc)
    hub_effect: str = "none"  # none | degraded | unusable
    block_slope_deg: float | None = None  # zone statice: blocate doar celulele cu pantă peste atât
    no_new_stops: bool = False  # pierderea legăturii: fără opriri noi
    max_duration_factor: float = 1.0  # pierderea legăturii: durata maximă redusă


@dataclass(frozen=True)
class MotionSegment:
    from_min: float
    velocity_ms: tuple[float, float]  # (vy spre sud, vx spre est)


@dataclass(frozen=True)
class HazardSpec:
    id: str
    kind: str
    scope: str  # local | global | point
    rev: int
    center_m: tuple[float, float] | None  # la t0_min; None la global / point
    axes_m: tuple[float, float]  # la t0_min
    theta_deg: float
    t0_min: float  # momentul la care sunt date centrul și semiaxele
    motion: tuple[MotionSegment, ...]
    alpha_m_per_min: float
    cap_axes_m: tuple[float, float]
    start_min: float
    end_min: float  # math.inf = fără sfârșit
    effects: Effects
    sigma_rel: float
    horizon_cap_min: float
    intensity: float = 0.8  # 0..1, pentru compatibilitatea cu hazards.Hazard (profilul parabolic)
    source: str = "scenario"  # scenario | user | forecast
    warning_min: float = 0.0  # furtuna solară: efectul începe la start_min + warning_min
    ignored: bool = False  # pericol mic: rămâne în listă, nu replanifică

    # --- cinematică (§4: pe segmente, creștere aditivă cu plafon) ---

    def active(self, t: float) -> bool:
        return self.start_min - 1e-9 <= t <= self.end_min + 1e-9

    def velocity_at(self, t: float) -> tuple[float, float]:
        v = (0.0, 0.0)
        for seg in self.motion:
            if seg.from_min <= t + 1e-9:
                v = seg.velocity_ms
        return v

    def center_at(self, t: float) -> tuple[float, float] | None:
        """P(t) = P0 + ∫ v dt pe segmentele de mișcare, de la t0_min (și înapoi, dacă t < t0)."""
        if self.center_m is None:
            return None
        lo, hi, sign = (self.t0_min, t, 1.0) if t >= self.t0_min else (t, self.t0_min, -1.0)
        cy, cx = self.center_m
        bounds = [s.from_min for s in self.motion] + [math.inf]
        for i, seg in enumerate(self.motion):
            a, b = max(lo, seg.from_min), min(hi, bounds[i + 1])
            if b > a:
                cy += sign * seg.velocity_ms[0] * (b - a) * 60.0
                cx += sign * seg.velocity_ms[1] * (b - a) * 60.0
        return (cy, cx)

    def axes_at(self, t: float) -> tuple[float, float]:
        """a(t) = min(a0 + α·(t − t0), a_cap); la fel pentru b. Înainte de t0 nu scade sub a0."""
        dt = max(0.0, t - self.t0_min)
        a = min(self.axes_m[0] + self.alpha_m_per_min * dt, max(self.cap_axes_m[0], self.axes_m[0]))
        b = min(self.axes_m[1] + self.alpha_m_per_min * dt, max(self.cap_axes_m[1], self.axes_m[1]))
        return (a, b)

    def is_geometric(self) -> bool:
        """Pericolul blochează geometric (local, cu centru, neignorat)?"""
        return self.scope == "local" and self.center_m is not None and not self.ignored


# Clasele implicite (§2.1). Valori nivel C dacă nu au sursă (lista din rol2.md, „Presupuneri”).
CLASS_DEFAULTS: dict[str, dict] = {
    # Mobil local. ALPHA: 15 m/min vârtej, 30 m/min front (§11, C, de calibrat pe MEDA).
    "dust_devil": {"scope": "local", "alpha": 15.0, "sigma_rel": hz.SIGMA_REL, "intensity": 0.9, "axes": (65.0, 65.0),
                   "effects": Effects(block="core", soft_halo=True, speed_mult=0.5)},
    "local_storm": {"scope": "local", "alpha": 30.0, "sigma_rel": hz.SIGMA_REL, "intensity": 0.7, "axes": (15000.0, 2500.0),
                    "effects": Effects(block="core", soft_halo=True, speed_mult=0.5)},
    "custom": {"scope": "local", "alpha": 15.0, "sigma_rel": 0.2, "intensity": 0.8,
               "effects": Effects(block="core", soft_halo=True, speed_mult=0.6)},
    # Zone statice: cutremur ~300 m (C), resturi de aterizare ±150 m (registru); blocate doar pantele > 15°.
    "marsquake": {"scope": "local", "alpha": 0.0, "sigma_rel": 0.0, "intensity": 1.0, "axes": (300.0, 300.0),
                  "duration": 60.0, "effects": Effects(block="core", soft_halo=True, block_slope_deg=15.0)},
    "debris": {"scope": "local", "alpha": 0.0, "sigma_rel": 0.0, "intensity": 1.0, "axes": (150.0, 150.0),
               "effects": Effects(block="all", soft_halo=True)},
    # Global. Regională: tau ~3 mută apusul (daylight.effective_sunset_min: 30 min pe unitate de tau peste
    # 0,5 → −75 min), viteza × 0,8 (C). Solară: doza × 2,5 (registru [S14][S15]), după avertizare 30 min, ~48 h.
    "regional_storm": {"scope": "global", "alpha": 0.0, "sigma_rel": 0.0, "intensity": 0.9,
                       "effects": Effects(block="none", soft_halo=False, speed_mult=0.8, daylight_shift_min=-75.0)},
    "solar_particle_event": {"scope": "global", "alpha": 0.0, "sigma_rel": 0.0, "intensity": 1.0,
                             "duration": 2880.0, "warning": 30.0,
                             "effects": Effects(block="none", soft_halo=False, dose_mult=2.5)},
    # Evenimente de stare (point): modifică astronautul.
    "suit_leak": {"scope": "point", "effects": Effects(block="none", soft_halo=False, o2_add_pct_min=0.15)},
    "fatigue": {"scope": "point", "effects": Effects(block="none", soft_halo=False, speed_mult=0.8, o2_mult=1.15)},
    # presupunere (C): coechipier rănit, viteză × 0,5 și O₂ × 1,5 (decizia echipei, până la o sursă).
    "crewmate_injured": {"scope": "point", "effects": Effects(block="none", soft_halo=False, speed_mult=0.5, o2_mult=1.5)},
    # Informativ: fără efect pe rutare; fără opriri noi, durata maximă redusă (C: × 0,8).
    "comm_loss": {"scope": "global", "effects": Effects(block="none", soft_halo=False, no_new_stops=True,
                                                        max_duration_factor=0.8)},
}
STATE_KINDS = ("suit_leak", "fatigue", "crewmate_injured")


@dataclass
class Result:
    """Rezultatul unei normalizări sau al unei operații pe registru (fără excepții)."""

    spec: HazardSpec | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    op: str | None = None  # operația efectivă (add / update / remove)

    @property
    def ok(self) -> bool:
        return self.error is None


def _num(value, default: float | None = None) -> float | None:
    """Număr finit sau None/NaN marcat; șirurile numerice sunt acceptate."""
    if value is None:
        return default
    try:
        x = float(value)
    except (TypeError, ValueError):
        return math.nan
    return x


def _pair(value, default=None):
    if value is None:
        return default
    try:
        a, b = value
        return (_num(a), _num(b))
    except (TypeError, ValueError):
        return (math.nan, math.nan)


def _center(raw, cell_size_m: float):
    """{row, col} (celulă, la centru) sau [y, x] / {y_m, x_m} în metri; None dacă lipsește."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        if "row" in raw and "col" in raw:
            r, c = _num(raw["row"]), _num(raw["col"])
            return ((r + 0.5) * cell_size_m, (c + 0.5) * cell_size_m)
        if "y_m" in raw and "x_m" in raw:
            return (_num(raw["y_m"]), _num(raw["x_m"]))
        return (math.nan, math.nan)
    return _pair(raw, (math.nan, math.nan))


def _finite(*values) -> bool:
    return all(v is not None and math.isfinite(v) for v in values)


def normalize(raw: dict, kind: str | None = None, *, cell_size_m: float = 20.0, t_now: float = 0.0,
              shape: tuple[int, int] | None = None, hazard_id: str | None = None, rev: int = 1,
              base: HazardSpec | None = None) -> Result:
    """Construiește un HazardSpec din formatul V2 (§2.3) sau din parametrii vechi (live_event.json).

    `base`: specificația existentă la un `update` (câmpurile lipsă se iau din ea, nu din clasă).
    Reguli (§2.1): semiaxe ≥ celula; viteze plafonate la V_HAZARD_MAX_MS (avertisment); sigma_rel în
    [0, 1]; alpha ≥ 0; durată > 0; NaN → respins (ERR_NAN); semiaxe negative → ERR_SHAPE; pericol local
    fără centru → ERR_CENTER; < IGNORE_RADIUS_M → `ignored`; acoperire > GLOBAL_COVERAGE → global.
    """
    if not isinstance(raw, dict):
        return Result(error=ERR_SHAPE)
    warnings: list[str] = []
    kind = str(raw.get("kind") or kind or (base.kind if base else "custom"))
    if kind not in CLASS_DEFAULTS:
        warnings.append(WARN_KIND)
    defaults = CLASS_DEFAULTS.get(kind, CLASS_DEFAULTS["custom"])
    shape_raw = raw.get("shape") if isinstance(raw.get("shape"), dict) else {}
    motion_raw = raw.get("motion")
    growth = raw.get("growth") if isinstance(raw.get("growth"), dict) else {}
    lifetime = raw.get("lifetime") if isinstance(raw.get("lifetime"), dict) else {}
    effects_raw = raw.get("effects") if isinstance(raw.get("effects"), dict) else {}
    unc = raw.get("uncertainty") if isinstance(raw.get("uncertainty"), dict) else {}

    scope = str(raw.get("scope") or (base.scope if base else defaults["scope"]))
    if scope not in SCOPES:
        scope = defaults["scope"]

    # Geometria (formatul V2 sub `shape`, formatul vechi direct în params).
    center = _center(shape_raw.get("center", raw.get("center")), cell_size_m)
    if center is None and base is not None:
        center = base.center_at(t_now)
    axes = _pair(shape_raw.get("axes_m", raw.get("axes_m")))
    if axes is None:
        axes = base.axes_at(t_now) if base is not None else defaults.get("axes", (500.0, 500.0))
    theta = _num(shape_raw.get("theta_deg", raw.get("theta_deg", raw.get("angle_deg"))),
                 base.theta_deg if base else 0.0)
    intensity = _num(raw.get("intensity"), base.intensity if base else defaults.get("intensity", 0.8))

    # Mișcarea: listă de segmente (V2) sau o viteză (vechi). La update fără viteză: mișcarea veche.
    segments: list[tuple[float, tuple]] = []
    if isinstance(motion_raw, list) and motion_raw:
        for seg in motion_raw:
            if not isinstance(seg, dict):
                return Result(error=ERR_SHAPE, warnings=warnings)
            segments.append((_num(seg.get("from_min"), t_now), _pair(seg.get("velocity_ms"), (0.0, 0.0))))
    elif raw.get("velocity_ms") is not None:
        segments.append((t_now, _pair(raw.get("velocity_ms"), (0.0, 0.0))))
    elif base is not None:
        segments = [(t_now, base.velocity_at(t_now))] + [
            (s.from_min, s.velocity_ms) for s in base.motion if s.from_min > t_now]
    else:
        segments.append((t_now, (0.0, 0.0)))

    alpha = _num(growth.get("alpha_m_per_min", raw.get("alpha_m_per_min")),
                 base.alpha_m_per_min if base else defaults.get("alpha", 0.0))
    cap = _pair(growth.get("cap_axes_m", raw.get("cap_axes_m")))
    start = _num(lifetime.get("start_min", raw.get("start_min")), base.start_min if base else t_now)
    duration = _num(lifetime.get("duration_min", raw.get("duration_min")))
    end = _num(lifetime.get("end_min", raw.get("end_min")))
    sigma = _num(unc.get("sigma_rel", raw.get("sigma_rel")), base.sigma_rel if base else defaults.get("sigma_rel", 0.0))
    cap_h = _num(unc.get("horizon_cap_min", raw.get("horizon_cap_min")), base.horizon_cap_min if base else H_CONE_MIN)

    numbers = [theta, intensity, alpha, sigma, cap_h, start]
    numbers += [v for _, vel in segments for v in vel] + [t for t, _ in segments]
    numbers += list(axes)
    if center is not None:
        numbers += list(center)
    if cap is not None:
        numbers += list(cap)
    if any(x is None or not math.isfinite(x) for x in numbers) or any(
            x is not None and math.isnan(x) for x in (duration, end)):
        return Result(error=ERR_NAN, warnings=warnings)
    if axes[0] < 0 or axes[1] < 0:
        return Result(error=ERR_SHAPE, warnings=warnings)
    if scope == "local" and center is None:
        return Result(error=ERR_CENTER, warnings=warnings)

    small = max(axes) < IGNORE_RADIUS_M
    axes = (max(axes[0], cell_size_m), max(axes[1], cell_size_m))
    motion = []
    for t_from, (vy, vx) in sorted(segments, key=lambda s: s[0]):
        speed = math.hypot(vy, vx)
        if speed > V_HAZARD_MAX_MS:
            vy, vx = vy * V_HAZARD_MAX_MS / speed, vx * V_HAZARD_MAX_MS / speed
            if WARN_SPEED not in warnings:
                warnings.append(WARN_SPEED)
        motion.append(MotionSegment(float(t_from), (float(vy), float(vx))))
    alpha = max(0.0, alpha)
    sigma = min(1.0, max(0.0, sigma))
    cap_h = max(0.0, cap_h)
    intensity = min(1.0, max(0.0, intensity))
    if cap is None:
        cap = base.cap_axes_m if (base is not None and "growth" not in raw and "alpha_m_per_min" not in raw) else (
            axes[0] + alpha * H_CONE_MIN, axes[1] + alpha * H_CONE_MIN)
    cap = (max(cap[0], axes[0]), max(cap[1], axes[1]))
    if end is not None and end > start:
        end_min = end
    elif duration is not None and duration > 0:
        end_min = start + duration
    elif base is not None:
        end_min = base.end_min
    else:
        end_min = start + defaults["duration"] if "duration" in defaults else math.inf

    effects = _effects(effects_raw, raw, base.effects if base else defaults["effects"])
    spec = HazardSpec(
        id=str(hazard_id or raw.get("id") or (base.id if base else f"{kind}_{int(t_now)}")),
        kind=kind, scope=scope, rev=int(rev), center_m=center if scope == "local" else None,
        axes_m=axes, theta_deg=float(theta), t0_min=float(t_now), motion=tuple(motion),
        alpha_m_per_min=float(alpha), cap_axes_m=cap, start_min=float(start), end_min=float(end_min),
        effects=effects, sigma_rel=float(sigma), horizon_cap_min=float(cap_h), intensity=float(intensity),
        source=str(raw.get("source") or (base.source if base else "scenario")),
        warning_min=float(_num(raw.get("warning_min"), base.warning_min if base else defaults.get("warning", 0.0))),
        ignored=bool(small and scope == "local"),
    )
    if spec.ignored:
        warnings.append(WARN_IGNORED)
    if spec.scope == "local" and shape is not None and coverage(spec, shape, cell_size_m, t_now) > GLOBAL_COVERAGE:
        spec = replace(spec, scope="global")
        warnings.append(WARN_GLOBAL)
    return Result(spec=spec, warnings=warnings, op="add")


def _effects(raw: dict, top: dict, base: Effects) -> Effects:
    """Efectele: `effects` (V2) peste cele de bază; `hub_effect` poate sta și la nivelul de sus."""
    values = {}
    for name in Effects.__dataclass_fields__:
        if name in raw:
            values[name] = raw[name]
    if "hub_effect" in top and "hub_effect" not in values:
        values["hub_effect"] = top["hub_effect"]
    out = replace(base, **values)
    block = out.block if out.block in BLOCKS else base.block
    hub = out.hub_effect if out.hub_effect in HUB_EFFECTS else "none"
    num = {k: _num(getattr(out, k), getattr(base, k)) for k in
           ("core_fraction", "speed_mult", "o2_mult", "o2_add_pct_min", "dose_mult", "daylight_shift_min",
            "exposure_limit_min", "max_duration_factor")}
    for k, v in num.items():
        if v is None or not math.isfinite(v):
            num[k] = getattr(base, k)
    num["core_fraction"] = min(1.0, max(0.0, num["core_fraction"]))
    for k in ("speed_mult", "o2_mult", "dose_mult", "max_duration_factor"):
        num[k] = max(0.05, num[k])  # un multiplicator ≤ 0 n-ar avea sens fizic
    num["o2_add_pct_min"] = max(0.0, num["o2_add_pct_min"])
    num["exposure_limit_min"] = max(0.0, num["exposure_limit_min"])
    return replace(out, block=block, hub_effect=hub, soft_halo=bool(out.soft_halo),
                   no_new_stops=bool(out.no_new_stops), **num)


def coverage(spec: HazardSpec, shape: tuple[int, int], cell_size_m: float, t_now: float) -> float:
    """Fracția maximă din hartă acoperită de elipsă pe orizontul H_WATCH (aproximare pe 40 × 40 de puncte)."""
    if spec.center_m is None:
        return 1.0 if spec.scope == "global" else 0.0
    rows, cols = shape
    n = COVERAGE_SAMPLES
    ys = [(i + 0.5) / n * rows * cell_size_m for i in range(n)]
    xs = [(j + 0.5) / n * cols * cell_size_m for j in range(n)]
    best, t = 0.0, max(t_now, spec.start_min)
    while t <= t_now + H_WATCH_MIN + 1e-9:
        if spec.active(t):
            cy, cx = spec.center_at(t)
            a, b = spec.axes_at(t)
            th = math.radians(spec.theta_deg)
            ct, st = math.cos(th), math.sin(th)
            inside = 0
            for y in ys:
                dy = y - cy
                for x in xs:
                    dx = x - cx
                    u, v = dx * ct + dy * st, -dx * st + dy * ct
                    inside += (u / a) ** 2 + (v / b) ** 2 <= 1.0
            best = max(best, inside / (n * n))
        t += COVERAGE_STEP_MIN
    return best


def reanchor(spec: HazardSpec, t_now: float) -> HazardSpec:
    """Poziția și semiaxele prezise la t_now devin noua origine (fără salt de poziție)."""
    center = spec.center_at(t_now)
    axes = spec.axes_at(t_now)
    motion = [MotionSegment(t_now, spec.velocity_at(t_now))] + [s for s in spec.motion if s.from_min > t_now]
    return replace(spec, center_m=center, axes_m=axes, t0_min=float(t_now), motion=tuple(motion))


class HazardRegistry:
    """Pericolele active, după id; `apply` face add / update / remove cu `rev` (§2.2). Fără excepții."""

    def __init__(self, cell_size_m: float = 20.0, shape: tuple[int, int] | None = None):
        self.cell_size_m = float(cell_size_m)
        self.shape = shape
        self.specs: dict[str, HazardSpec] = {}
        self.log: list[tuple[float, str, str, int, list[str]]] = []  # (t, op, id, rev, avertismente)

    def apply(self, op: str, payload: dict | None, t_now: float, kind: str | None = None) -> Result:
        payload = dict(payload or {})
        if op not in OPS:
            return Result(error=ERR_OP)
        hid = payload.get("id")
        if op == "remove":
            if hid not in self.specs:
                return Result(error=ERR_UNKNOWN_ID, op="remove")
            spec = self.specs.pop(hid)
            self.log.append((t_now, "remove", hid, spec.rev, []))
            return Result(spec=spec, op="remove")
        warnings: list[str] = []
        if op == "add" and hid in self.specs:
            op, warnings = "update", [WARN_ADD_AS_UPDATE]
        elif op == "update" and hid not in self.specs:
            op, warnings = "add", [WARN_UPDATE_AS_ADD]
        if op == "update":
            old = reanchor(self.specs[hid], t_now)
            res = normalize(payload, kind, cell_size_m=self.cell_size_m, t_now=t_now, shape=self.shape,
                            hazard_id=hid, rev=old.rev + 1, base=old)
        else:
            res = normalize(payload, kind, cell_size_m=self.cell_size_m, t_now=t_now, shape=self.shape,
                            hazard_id=hid, rev=1)
        res.warnings = warnings + res.warnings
        res.op = op
        if res.ok:
            self.specs[res.spec.id] = res.spec
            self.log.append((t_now, op, res.spec.id, res.spec.rev, list(res.warnings)))
        return res

    def active(self, t: float) -> list[HazardSpec]:
        """Pericolele active la t, sortate după id (ordine totală)."""
        return [self.specs[k] for k in sorted(self.specs) if self.specs[k].active(t)]

    def revisions(self) -> tuple[tuple[str, int], ...]:
        """(id, rev) sortate: intră în hash-ul stării canonice."""
        return tuple((k, self.specs[k].rev) for k in sorted(self.specs))


def to_hazard(spec: HazardSpec, t: float) -> hz.Hazard:
    """Instantaneul la t, în modelul vechi (`hazards.Hazard`), pentru funcțiile existente."""
    if spec.center_m is None:  # global / point: fără geometrie, intensitate 0 (nu blochează nimic)
        return hz.Hazard(spec.id, spec.kind, (0.0, 0.0), (1.0, 1.0), spec.theta_deg, 0.0, (0.0, 0.0), float(t))
    return hz.Hazard(spec.id, spec.kind, spec.center_at(t), spec.axes_at(t), spec.theta_deg, spec.intensity,
                     spec.velocity_at(t), float(t))


def from_hazard(h: hz.Hazard, *, rev: int = 1, cell_size_m: float = 20.0) -> HazardSpec:
    """Specificația echivalentă unui `hazards.Hazard` (clasa implicită a tipului lui)."""
    res = normalize({"id": h.id, "kind": h.kind, "shape": {"center": [h.center_m[0], h.center_m[1]],
                                                           "axes_m": list(h.axes_m), "theta_deg": h.angle_deg},
                     "motion": [{"from_min": h.t0_min, "velocity_ms": list(h.velocity_ms)}],
                     "intensity": h.intensity}, h.kind, cell_size_m=cell_size_m, t_now=h.t0_min, rev=rev)
    return res.spec


def to_contract(spec: HazardSpec, t: float, cell_size_m: float) -> dict:
    """Forma `tick.hazards[]` din live_messages.json, plus câmpurile opționale `rev`, `scope`, `ignored`."""
    if spec.center_m is None:
        out = {"id": spec.id, "kind": spec.kind, "intensity": float(spec.intensity), "forecast": []}
    else:
        out = hz.to_contract(to_hazard(spec, t), t, cell_size_m)
    out.update({"rev": spec.rev, "scope": spec.scope, "ignored": spec.ignored})
    return out
