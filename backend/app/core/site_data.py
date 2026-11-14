"""Încarcă situl de pe disc: meta.json + grilele .npy."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import SITE_ID, site_dir


@dataclass
class Site:
    meta: dict
    layers: dict[str, np.ndarray]
    path: Path

    @property
    def shape(self) -> tuple[int, int]:
        return tuple(self.meta["shape"])

    @property
    def cell_size_m(self) -> float:
        return float(self.meta["cell_size_m"])

    @property
    def habitat(self) -> tuple[int, int]:
        h = self.meta["habitat"]
        return (h["row"], h["col"])

    def value_at(self, row: int, col: int) -> dict:
        """Valorile tuturor straturilor într-o celulă (pentru GET /api/point)."""
        return {name: grid[row, col].item() for name, grid in self.layers.items()}


def load_site(directory: Path) -> Site:
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    layers = {
        name: np.load(directory / spec["file"])
        for name, spec in meta["layers"].items()
        if (directory / spec["file"]).exists()
    }
    return Site(meta=meta, layers=layers, path=directory)


@lru_cache(maxsize=4)
def get_site(site_id: str = SITE_ID) -> Site | None:
    """Situl activ, sau None dacă pipeline-ul nu l-a generat încă."""
    directory = site_dir(site_id)
    if not (directory / "meta.json").exists():
        return None
    return load_site(directory)
