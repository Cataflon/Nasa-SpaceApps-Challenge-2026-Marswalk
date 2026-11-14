"""Caută DTM-urile HiRISE și CTX pentru Jezero în STAC-ul USGS și decupează fereastra de 10×10 km.

Citește doar fereastra din COG (rasterio), fără să descarce fișierele întregi.

Rulare:
  python pipeline/fetch_stac.py --list-collections
  python pipeline/fetch_stac.py --collection <id> --out data/raw/jezero

Documentație: https://stac.astrogeology.usgs.gov/docs/data/mars/hirise_dtms
"""

import argparse
from pathlib import Path

STAC_API = "https://stac.astrogeology.usgs.gov/api/"

# Centrul zonei de lucru (frontul deltei Jezero). TODO (rolul 1): verificați pe Mars Trek.
CENTER_LAT, CENTER_LON = 18.46, 77.42
HALF_SIZE_KM = 5.0
KM_PER_DEG_LAT = 59.27  # raza Marte 3396 km


def bbox() -> tuple[float, float, float, float]:
    import math

    dlat = HALF_SIZE_KM / KM_PER_DEG_LAT
    dlon = HALF_SIZE_KM / (KM_PER_DEG_LAT * math.cos(math.radians(CENTER_LAT)))
    return (CENTER_LON - dlon, CENTER_LAT - dlat, CENTER_LON + dlon, CENTER_LAT + dlat)


def list_collections() -> None:
    from pystac_client import Client

    client = Client.open(STAC_API)
    for col in client.get_collections():
        if any(k in col.id.lower() for k in ("hirise", "ctx")):
            print(f"{col.id:<60} {col.title}")


def search(collection: str) -> list:
    from pystac_client import Client

    client = Client.open(STAC_API)
    items = list(client.search(collections=[collection], bbox=bbox()).items())
    for it in items:
        print(it.id, list(it.assets))
    return items


def crop(item, asset_key: str, out: Path) -> Path:
    """TODO (rolul 1): rasterio.open(href) -> transformă bbox în CRS-ul rasterului ->
    rasterio.windows.from_bounds -> read(window=...) -> scrie GeoTIFF în `out`."""
    raise NotImplementedError


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--list-collections", action="store_true")
    p.add_argument("--collection")
    p.add_argument("--out", type=Path, default=Path("data/raw/jezero"))
    args = p.parse_args()

    print("bbox (lon_min, lat_min, lon_max, lat_max):", tuple(round(v, 4) for v in bbox()))
    if args.list_collections:
        list_collections()
    elif args.collection:
        search(args.collection)


if __name__ == "__main__":
    main()
