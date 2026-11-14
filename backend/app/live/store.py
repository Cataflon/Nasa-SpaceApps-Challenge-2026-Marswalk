"""Traseele planificate, ținute în memorie după `route_id` (folosite de motorul live)."""

import copy
import threading


class RouteStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._routes: dict[str, dict] = {}
        self._counter = 0
        self._latest: str | None = None

    def add(self, route: dict) -> str:
        """Salvează traseul sub un id nou (`plan_0`, `plan_1`, …) și îl scrie în `route["route_id"]`."""
        with self._lock:
            route_id = f"plan_{self._counter}"
            self._counter += 1
            route["route_id"] = route_id
            self._routes[route_id] = copy.deepcopy(route)
            self._latest = route_id
            return route_id

    def get(self, route_id: str) -> dict | None:
        with self._lock:
            route = self._routes.get(route_id)
            return copy.deepcopy(route) if route is not None else None

    def latest(self) -> dict | None:
        with self._lock:
            return copy.deepcopy(self._routes[self._latest]) if self._latest else None

    def clear(self) -> None:
        with self._lock:
            self._routes.clear()
            self._counter = 0
            self._latest = None


routes = RouteStore()
