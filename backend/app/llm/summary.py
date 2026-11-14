"""Rezumatul compact al unei decizii, trimis lui `explain()` (LLM sau șablon).

Rezumatul e și cheia de cache, deci trebuie să fie determinist:
cifre rotunjite, ordine stabilă, fără câmpuri `None`.
"""

from app.core.types import Alternative, Decision, Limits

NO_ALTERNATIVE = "none"  # id-ul folosit când nu există nicio rută (EMERGENCY fără întoarcere)


def _minutes(x: float) -> int:
    return int(round(float(x)))


def _one_decimal(x: float) -> float:
    return round(float(x), 1)


def _find(alternatives: list[Alternative], alt_id: str | None) -> Alternative | None:
    return next((a for a in alternatives if a.id == alt_id), None)


def build_summary(
    decision: Decision,
    *,
    t_min: float,
    hazard_kind: str | None = None,
    eta_hazard_min: float | None = None,
    limits: Limits = Limits(),
) -> dict:
    """Transformă o decizie a regulii în dict-ul pentru `llm.explain()`.

    - `decision` / `alternative_id`: copiate din decizie (`"none"` dacă nu e aleasă nicio rută).
    - `alternative_ids`: id-urile valide + cea aleasă, chiar dacă e invalidă (la EMERGENCY),
      ca LLM-ul să o poată scrie în enum-ul schemei JSON.
    - Cifrele alternativei alese stau la primul nivel, ca șabloanele să le folosească direct.
    - `rejected`: alternativele respinse de validator și de ce.
    """
    chosen_id = decision.alternative_id or NO_ALTERNATIVE
    chosen = _find(decision.alternatives, decision.alternative_id)

    alternative_ids: list[str] = []
    for alt in decision.alternatives:
        if alt.valid and alt.id not in alternative_ids:
            alternative_ids.append(alt.id)
    if chosen_id not in alternative_ids:
        alternative_ids.append(chosen_id)

    summary: dict = {
        "decision": decision.decision,
        "alternative_id": chosen_id,
        "alternative_ids": alternative_ids,
        "reason_code": decision.reason_code,
        "t_min": _minutes(t_min),
        "hazard": hazard_kind,
        "eta_hazard_min": _minutes(eta_hazard_min) if eta_hazard_min is not None else None,
        "o2_reserve_pct": _one_decimal(limits.o2_reserve_pct),
    }

    if chosen is not None:
        summary.update(
            {
                "extra_min": _minutes(chosen.extra_min),
                "o2_end_pct": _one_decimal(chosen.o2_end_pct),
                "dose_msv": round(float(chosen.dose_msv), 2),
                "science_lost": list(chosen.science_lost) or None,
            }
        )

    rejected = [{"id": a.id, "why": list(a.violations)} for a in decision.alternatives if not a.valid]
    if rejected:
        summary["rejected"] = rejected

    return {k: v for k, v in summary.items() if v is not None}
