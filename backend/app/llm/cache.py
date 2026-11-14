"""Cache după hash-ul stării, ca demo-ul și benchmark-ul să se repete identic."""

import hashlib
import json
from pathlib import Path

from app.config import DATA_DIR

CACHE_FILE = DATA_DIR / "cache" / "llm_explanations.json"


def key(summary: dict) -> str:
    canonical = json.dumps(summary, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExplanationCache:
    def __init__(self, path: Path = CACHE_FILE):
        self.path = path
        self.data: dict[str, dict] = {}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def get(self, summary: dict) -> dict | None:
        return self.data.get(key(summary))

    def put(self, summary: dict, value: dict) -> None:
        self.data[key(summary)] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")


cache = ExplanationCache()
