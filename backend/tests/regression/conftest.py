"""Fixture-uri comune pentru testele de contract (audit). Nu modifică tests/conftest.py.

- `contract(name)`: citește un exemplu din shared/contracts/;
- `synthetic_site`: situl sintetic de pe disc, sau skip dacă lipsește ori e mai vechi decât generatorul;
- `client`: TestClient pe aplicație, cu motorul live și stocul de trasee golite înainte și după;
- curățarea cache-urilor (costmap, planner) înainte de fiecare test.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "shared" / "contracts"


def load_contract(name: str):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def generator_version() -> int:
    text = (ROOT / "pipeline" / "make_synthetic_site.py").read_text(encoding="utf-8")
    return int(re.search(r"^GENERATOR_VERSION\s*=\s*(\d+)", text, re.M).group(1))


def json_kind(value) -> str:
    """Tipul JSON al unei valori: number (int și float sunt același tip în JSON), string, bool, null, object, array."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    return type(value).__name__  # ex. numpy.float32: tip nepermis în JSON


def shape_diff(example, actual, path="$", nullable=(), optional=()) -> list[str]:
    """Diferențele recursive de formă între exemplul din contract și ieșirea reală.

    Cheile care încep cu `_` (note) se ignoră. `nullable`: căi unde null e permis în locul tipului.
    `optional`: căi de chei în plus permise (câmpuri noi, opționale, anunțate în README).
    """
    out = []
    ek, ak = json_kind(example), json_kind(actual)
    if ek != ak:
        if not (ak == "null" and path in nullable) and not (ek == "null" and path in nullable):
            out.append(f"{path}: contract={ek} real={ak}")
        return out
    if ek == "object":
        e_keys = {k for k in example if not k.startswith("_")}
        a_keys = set(actual)
        for k in sorted(e_keys - a_keys):
            out.append(f"{path}.{k}: lipsește")
        for k in sorted(a_keys - e_keys):
            if f"{path}.{k}" not in optional:
                out.append(f"{path}.{k}: cheie în plus")
        for k in sorted(e_keys & a_keys):
            out += shape_diff(example[k], actual[k], f"{path}.{k}", nullable, optional)
    elif ek == "array" and example and actual:
        # Elementele exemplului au aceeași formă; comparăm primul element real cu primul din exemplu.
        out += shape_diff(example[0], actual[0], f"{path}[]", nullable, optional)
    return out


def assert_plain_json(value, path="$"):
    """Doar tipuri JSON Python (fără numpy, tupluri ok), serializabil cu allow_nan=False."""
    kind = json_kind(value)
    assert kind in {"null", "bool", "number", "string", "object", "array"}, f"{path}: tip nepermis {kind}"
    if isinstance(value, dict):
        for k, v in value.items():
            assert isinstance(k, str), f"{path}: cheie non-șir {k!r}"
            assert_plain_json(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            assert_plain_json(v, f"{path}[{i}]")
    json.dumps(value, allow_nan=False)


@pytest.fixture
def contract():
    return load_contract


@pytest.fixture
def audit():
    """Funcțiile ajutătoare, ca fixture (fără import din conftest, care nu e pachet)."""
    from types import SimpleNamespace

    return SimpleNamespace(shape_diff=shape_diff, assert_plain_json=assert_plain_json, json_kind=json_kind,
                           load_contract=load_contract, root=ROOT)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Golește cache-ul hărții de cost (ieftin). Cache-ul planner-ului (Dijkstra, ~1 s) e legat de
    obiectul sit și e determinist, deci îl păstrăm între teste pe același sit de sesiune."""
    from app.core import costmap

    costmap.clear_cost_cache()
    yield
    costmap.clear_cost_cache()


@pytest.fixture(scope="session")
def synthetic_site():
    from app.core.site_data import load_site

    directory = ROOT / "data" / "synthetic"
    if not (directory / "meta.json").exists():
        pytest.skip("data/synthetic/meta.json lipsește: rulați python pipeline/make_synthetic_site.py")
    site = load_site(directory)
    found, expected = site.meta.get("generator_version", 1), generator_version()
    if found != expected:
        pytest.skip(f"situl sintetic de pe disc e v{found}, generatorul e v{expected}: regenerați-l")
    return site


@pytest.fixture
def client(monkeypatch, synthetic_site):
    """TestClient fără lifespan (fără buclă run() și fără Ollama); situl sintetic proaspăt."""
    from fastapi.testclient import TestClient

    from app.api import main
    from app.live.engine import engine
    from app.live.store import routes

    monkeypatch.setattr(main, "get_site", lambda: synthetic_site)
    monkeypatch.setattr(engine, "site_provider", lambda: synthetic_site)
    routes.clear()
    engine.reset()
    yield TestClient(main.app, raise_server_exceptions=False)
    engine.reset()
    routes.clear()
