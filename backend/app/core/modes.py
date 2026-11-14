"""Mașina de moduri a buclei multi-rată (ARHITECTURA_RUTARE_V2 §3) și starea canonică.

Modul de alertă (NOMINAL / MONITOR / REACT / EMERGENCY) e separat de faza drumului (OUTBOUND /
INBOUND): faza nu schimbă eșantionarea. K = la câte tick-uri se re-evaluează periodic (nivelul 2).
"""

import hashlib
import json

from app.core.hazard_spec import H_REACT_MIN, H_WATCH_MIN

NOMINAL, MONITOR, REACT, EMERGENCY, SHELTERED = "NOMINAL", "MONITOR", "REACT", "EMERGENCY", "SHELTERED"
# presupunere (C, §3, §11): K pe mod (minute între re-evaluările periodice); SHELTERED = oprit.
K_BY_MODE = {NOMINAL: 15, MONITOR: 5, REACT: 1, EMERGENCY: 1, SHELTERED: 0}
# presupunere (C, rolul 3): un pericol nou ajuns la mai puțin de atât de astronaut declanșează nivelul 3.
PROXIMITY_M = 450.0
HASH_DECIMALS = 6  # §1.4: rotunjirea la 6 zecimale doar pe ieșiri și pe cheia de hash


def mode_for(contact_in_min: float | None, in_hazard: bool, state_event: bool, emergency: bool,
             sheltered: bool = False) -> str:
    """Modul după §3: EMERGENCY (niciun candidat valid) > REACT (contact ≤ H_REACT, astronaut în pericol,
    eveniment de stare) > MONITOR (contact în H_WATCH) > NOMINAL. SHELTERED: astronautul e în refugiu."""
    if sheltered:
        return SHELTERED
    if emergency:
        return EMERGENCY
    if in_hazard or state_event or (contact_in_min is not None and contact_in_min <= H_REACT_MIN + 1e-9):
        return REACT
    if contact_in_min is not None and contact_in_min <= H_WATCH_MIN + 1e-9:
        return MONITOR
    return NOMINAL


def state_hash(*, position, remaining, stops, revisions, o2_pct: float, dose_msv: float, phase: str,
               effects=()) -> str:
    """Hash-ul stării canonice (§3): poziția, traseul rămas, opririle, (id, rev) ale pericolelor, resursele,
    faza și efectele. Două tick-uri cu același hash refolosesc rezultatul replanificării."""
    def r(x):
        return round(float(x), HASH_DECIMALS)

    payload = {
        "pos": [r(position[0]), r(position[1])],
        "path": [[int(a), int(b)] for a, b in remaining],
        "stops": list(stops),
        "hazards": [[str(i), int(v)] for i, v in revisions],
        "o2": r(o2_pct), "dose": r(dose_msv), "phase": phase,
        "effects": [[r(e.start_min), r(min(e.end_min, 1e12)), r(e.speed_mult), r(e.o2_mult), r(e.o2_add_pct_min),
                     r(e.dose_mult), r(e.daylight_shift_min)] for e in effects],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
