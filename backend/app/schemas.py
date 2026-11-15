"""Modelele Pydantic pentru corpurile cererilor API.

Trebuie să rămână în sincron cu shared/contracts/*.json.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Preset = Literal["safe", "fast", "science"]
DecisionKind = Literal["CONTINUE", "REROUTE", "WAIT", "RETURN", "EMERGENCY"]
EventKind = Literal[
    "dust_devil",
    "local_storm",
    "regional_storm",
    "solar_particle_event",
    "marsquake",
    "suit_leak",
    "fatigue",
]


class CellModel(BaseModel):
    row: int
    col: int


class CustomStop(BaseModel):
    """Un punct propriu de pe hartă (contractul frontendului 1.1, §5). Nu primește valoare științifică
    aleasă de utilizator."""

    model_config = ConfigDict(extra="ignore")
    id: Annotated[str, Field(pattern=r"^note_[A-Za-z0-9_-]+$", max_length=80)]
    name: Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[^<>]*$")]  # fără markup
    row: int
    col: int
    tag: Literal["waypoint", "science", "hazard", "shelter"] = "waypoint"
    dwell_min: Annotated[float, Field(ge=0, le=1440, allow_inf_nan=False)] = 0


class RouteRequest(BaseModel):
    start: CellModel
    # Id-uri, în ordinea cerută: din catalog (`clay_delta`) sau puncte proprii (`note_…`, definite în
    # `custom_stops`). Ordinea finală o decide planificatorul și e întoarsă în `stops`.
    stops: list[str] = Field(default_factory=list, max_length=100)
    custom_stops: list[CustomStop] = Field(default_factory=list, max_length=100)
    return_to_habitat: bool = True
    preset: Preset = "safe"
    start_time_min: float = Field(default=0, ge=0)
    # Orizontul motorului live (engine.MAX_DURATION_MIN = 720): un plan mai lung n-ar putea fi
    # simulat până la capăt, deci se respinge aici (contractul frontendului 1.1, §5).
    max_duration_min: float = Field(default=300, gt=0, le=720)


class LiveEvent(BaseModel):
    event: EventKind
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------- parametrii evenimentelor
# Câmpurile citite de motor, pe tip de eveniment (frontend/contracts/FRONTEND_BACKEND_ALGORITHM.md §8).
# Toate sunt opționale: lipsa unui câmp înseamnă valoarea implicită a motorului. Cheile necunoscute
# și valorile din afara intervalelor dau 422. Limitele sunt garduri tehnice, nu praguri științifice.

SemiAxis = Annotated[float, Field(ge=1, le=100_000, allow_inf_nan=False)]
Speed = Annotated[float, Field(ge=-100, le=100, allow_inf_nan=False)]


class _EventParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Literal["low", "medium", "high"] | None = None


class SpatialEventParams(_EventParams):
    """local_storm, regional_storm, dust_devil, marsquake. `center` se verifică față de grilă în rută."""

    center: CellModel | None = None
    axes_m: tuple[SemiAxis, SemiAxis] | None = None  # semiaxe [a, b], nu diametre
    angle_deg: Annotated[float, Field(ge=0, le=360, allow_inf_nan=False)] | None = None
    intensity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    velocity_ms: tuple[Speed, Speed] | None = None  # [spre sud, spre est]
    # Momentul vârfului și durata semnalului în senzori (scenario.with_event), opționale.
    peak_after_min: Annotated[float, Field(ge=0, le=1440, allow_inf_nan=False)] | None = None
    duration_min: Annotated[float, Field(ge=1, le=10_080, allow_inf_nan=False)] | None = None


class SolarEventParams(_EventParams):
    dose_rate_multiplier: Annotated[float, Field(ge=1, le=100, allow_inf_nan=False)] | None = None
    duration_min: Annotated[float, Field(ge=1, le=10_080, allow_inf_nan=False)] | None = None


class SuitLeakParams(_EventParams):
    leak_pct_per_min: Annotated[float, Field(ge=0.001, le=10, allow_inf_nan=False)] | None = None


class FatigueParams(_EventParams):
    speed_factor: Annotated[float, Field(ge=0.01, le=1, allow_inf_nan=False)] | None = None


EVENT_PARAMS: dict[str, type[_EventParams]] = {
    "local_storm": SpatialEventParams,
    "regional_storm": SpatialEventParams,
    "dust_devil": SpatialEventParams,
    "marsquake": SpatialEventParams,
    "solar_particle_event": SolarEventParams,
    "suit_leak": SuitLeakParams,
    "fatigue": FatigueParams,
}


class LiveControl(BaseModel):
    action: Literal["start", "pause", "reset", "speed"]
    speed: float | None = Field(default=None, ge=1, le=60)
    route_id: str | None = None


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
