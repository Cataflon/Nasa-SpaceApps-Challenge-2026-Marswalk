"""Tipurile comune pentru algoritmi. Se schimbă doar cu acordul echipei."""

from dataclasses import dataclass, field

Cell = tuple[int, int]  # (row, col)


@dataclass(frozen=True)
class Limits:
    """Pragurile hard ale validatorului. Valorile sunt presupuneri până le verificăm."""

    o2_reserve_pct: float = 30.0
    sunset_margin_min: float = 30.0
    # A [S26]: 20°, conceptul NASA de operațiuni EVA pe Lună (registrul §4.1); decizia D1 a echipei.
    # Aceeași valoare ca meta.json (max_slope_deg), deci harta de cost și validatorul nu se contrazic.
    max_slope_deg: float = 20.0
    max_dose_msv: float = 1.0


@dataclass
class Budget:
    distance_m: float
    duration_min: float
    o2_start_pct: float
    o2_end_pct: float
    dose_msv: float
    return_by_min: float
    sunset_min: float
    # D4: câte o valoare pe fiecare punct din traseu (la sosirea în punct).
    eta_min: list[float] = field(default_factory=list)
    o2_pct: list[float] = field(default_factory=list)
    dose_msv_cum: list[float] = field(default_factory=list)


@dataclass
class Route:
    path: list[Cell]
    preset: str = "safe"
    budget: Budget | None = None
    max_slope_deg: float = 0.0


@dataclass
class Alternative:
    """O variantă candidată în timpul ieșirii live (CONTINUE, REROUTE, WAIT, RETURN)."""

    id: str
    kind: str
    path: list[Cell]
    extra_min: float
    o2_end_pct: float
    dose_msv: float
    risk: float  # 0..1, din modelul de pericol
    arrival_habitat_min: float
    sunset_min: float
    max_slope_deg: float = 0.0
    crosses_hazard: bool = False
    science_lost_value: float = 0.0  # 0..1, fracția din valoarea științifică pierdută
    science_lost: list[str] = field(default_factory=list)
    valid: bool = True
    violations: list[str] = field(default_factory=list)
    # --- ARHITECTURA_RUTARE_V2 (§6, §7): câmpuri noi, opționale ---
    exposure_min: float = 0.0  # expunerea în nucleu (minute), fără excepțiile V5 (ieșire, grația de refugiu)
    exposure_over_limit: bool = False  # V5: cel puțin un pericol depășește exposure_limit_min
    halo_integral: float = 0.0  # 0..1: expunerea în halou, normalizată
    beyond_pnr: bool = False  # V6: trece de punctul de neîntoarcere (cu efectele active)
    off_map: bool = False  # V7: iese din grilă sau are un segment estimat în afara ei
    refuge_unusable: bool = False  # V8: refugiul de destinație e `unusable` la sosire
    priority: int = 0  # prioritatea strategiei (tie-break după scor)
    # „step_back”: astronautul merge până la path[hold_index] (în afara drumului furtunii), stă acolo
    # hold_min minute, apoi continuă pe același path. None = fără oprire planificată.
    hold_index: int | None = None
    hold_min: float = 0.0
    merged_with: list[str] = field(default_factory=list)  # id-urile candidaților identici, deduplicați
    phase: str = "OUTBOUND"  # OUTBOUND | INBOUND
    flags: list[str] = field(default_factory=list)  # ex. ESTIMATED_OFF_MAP, IMPROVISED_REFUGE
    score: float | None = None  # S din §7 (completat la selecție)


@dataclass
class Decision:
    decision: str  # CONTINUE | REROUTE | WAIT | RETURN | EMERGENCY
    alternative_id: str | None
    reason_code: str
    alternatives: list[Alternative]
    # --- ARHITECTURA_RUTARE_V2 (§6, §9): câmpuri noi, opționale ---
    omitted: list[dict] = field(default_factory=list)  # [{"id", "reason"}] cu coduri stabile
    flags: list[str] = field(default_factory=list)  # ex. UNRECOVERABLE, NO_SHELTER, OFF_MAP
    phase: str = "OUTBOUND"
    relaxed: list[str] = field(default_factory=list)  # constrângerile relaxate la EMERGENCY
