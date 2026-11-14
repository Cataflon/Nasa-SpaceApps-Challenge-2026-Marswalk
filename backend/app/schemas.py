"""Modelele Pydantic pentru corpurile cererilor API.

Trebuie să rămână în sincron cu shared/contracts/*.json.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

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


class RouteRequest(BaseModel):
    start: CellModel
    stops: list[str] = Field(default_factory=list)
    return_to_habitat: bool = True
    preset: Preset = "safe"
    start_time_min: float = 0
    max_duration_min: float = 300


class LiveEvent(BaseModel):
    event: EventKind
    params: dict[str, Any] = Field(default_factory=dict)


class LiveControl(BaseModel):
    action: Literal["start", "pause", "reset", "speed"]
    speed: float | None = Field(default=None, ge=1, le=60)
    route_id: str | None = None


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
