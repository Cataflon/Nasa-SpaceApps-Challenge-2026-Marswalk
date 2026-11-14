"""Scriere PNG fără dependențe (doar zlib) + câteva colormap-uri simple pentru straturi."""

import struct
import zlib
from pathlib import Path

import numpy as np


def write_png(path: Path, rgba: np.ndarray) -> None:
    """rgba: (H, W, 3 sau 4) uint8."""
    h, w, c = rgba.shape
    color_type = {3: 2, 4: 6}[c]
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6))
    png += chunk(b"IEND", b"")
    Path(path).write_bytes(png)


def ramp(values: np.ndarray, stops: list[tuple[float, tuple[int, int, int]]], vmin=None, vmax=None) -> np.ndarray:
    """Colormap liniar prin puncte (poziție 0..1, culoare RGB)."""
    vmin = np.nanmin(values) if vmin is None else vmin
    vmax = np.nanmax(values) if vmax is None else vmax
    t = np.clip((values - vmin) / max(vmax - vmin, 1e-9), 0, 1)
    pos = np.array([s[0] for s in stops])
    out = np.zeros(values.shape + (3,), dtype=np.uint8)
    for ch in range(3):
        out[..., ch] = np.interp(t, pos, [s[1][ch] for s in stops]).astype(np.uint8)
    return out


def categorical(classes: np.ndarray, palette: dict[int, tuple[int, int, int, int]]) -> np.ndarray:
    out = np.zeros(classes.shape + (4,), dtype=np.uint8)
    for k, rgba in palette.items():
        out[classes == k] = rgba
    return out


def hillshade(elev: np.ndarray, cell_m: float, azimuth=315.0, altitude=45.0) -> np.ndarray:
    gy, gx = np.gradient(elev, cell_m)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(azimuth), np.radians(altitude)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(shade, 0, 1)
