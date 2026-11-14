"""Cache-ul pentru GET /api/benchmark (rolul 3).

`benchmark.run_benchmark(100, seed)` durează ≈ 1 min, deci se calculează o singură dată, la pornire,
pe un thread de fundal; până e gata, ruta întoarce 503 cu `Retry-After`, apoi rezultatul din cache.

Thread-ul nu calculează el însuși: pornește un proces separat (multiprocessing, „spawn”) și așteaptă
rezultatul. Un calcul de un minut în Python pe un thread din serverul web ar ține GIL-ul și ar încetini
bucla live (un tick pe secundă); într-un proces separat rulează pe alt nucleu. La oprirea serverului
procesul e terminat (`stop`).
"""

import logging
import multiprocessing as mp
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

POLL_S = 0.2  # cât de des verifică thread-ul dacă procesul separat mai trăiește


def _worker(conn, n: int, seed: int) -> None:
    """Rulează în procesul separat: calculează și trimite (ok, rezultat sau mesaj de eroare)."""
    try:
        from app.core.benchmark import run_benchmark

        conn.send((True, run_benchmark(n, seed)))
    except Exception as exc:  # orice eroare ajunge înapoi ca text, nu blochează serverul
        conn.send((False, f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


class BenchmarkCache:
    """Rezultatul lui run_benchmark(n, seed), calculat o dată, în fundal.

    `compute(n, seed)`: implicit None = run_benchmark într-un proces separat; testele dau o funcție
    proprie (rulată direct pe thread).
    """

    def __init__(self, n: int = 100, seed: int = 42, compute: Callable[[int, int], dict] | None = None):
        self.n, self.seed = n, seed
        self._compute = compute
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._proc = None
        self._stopped = False
        self.result: dict | None = None
        self.error: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Pornește calculul dacă nu e deja gata sau în curs. Idempotent."""
        with self._lock:
            if self.result is not None or self.running or self.error is not None:
                return
            self._stopped = False
            self._thread = threading.Thread(target=self._run, name="benchmark-cache", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """La oprirea serverului: termină procesul separat, dacă încă rulează."""
        self._stopped = True
        proc = self._proc
        if proc is not None and proc.is_alive():
            proc.terminate()

    def _run(self) -> None:
        try:
            result = self._compute(self.n, self.seed) if self._compute else self._in_subprocess()
        except Exception as exc:
            if not self._stopped:  # o oprire voită nu e o eroare: următorul start reia calculul
                self.error = f"{type(exc).__name__}: {exc}"
                log.warning("Benchmark-ul a eșuat: %s", self.error)
            return
        self.result = result

    def _in_subprocess(self) -> dict:
        ctx = mp.get_context("spawn")
        receiver, sender = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=_worker, args=(sender, self.n, self.seed), name="benchmark", daemon=True)
        proc.start()
        self._proc = proc
        sender.close()  # altfel recv() n-ar primi EOF dacă procesul moare
        if self._stopped:  # stop() a venit în timp ce procesul pornea
            proc.terminate()
        # Nu ne bazăm pe EOF: pe Windows, la „spawn”, părintele ține o copie a capătului de scriere
        # până când copilul o preia; dacă procesul e terminat înainte, recv() n-ar primi EOF niciodată.
        try:
            while not receiver.poll(POLL_S):
                if not proc.is_alive() and not receiver.poll(0):  # a murit fără să trimită nimic
                    raise RuntimeError("benchmark process stopped before returning a result")
            ok, payload = receiver.recv()
        except EOFError as exc:
            raise RuntimeError("benchmark process stopped before returning a result") from exc
        finally:
            receiver.close()
            proc.join(timeout=5)
        if not ok:
            raise RuntimeError(payload)
        return payload
