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


@dataclass
class Decision:
    decision: str  # CONTINUE | REROUTE | WAIT | RETURN | EMERGENCY
    alternative_id: str | None
    reason_code: str
    alternatives: list[Alternative]
