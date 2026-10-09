"""Bewertungslogik des Service Checks (reine Funktionen, ohne DB-Zugriff).

Antworten pro Parameter: yes (erfüllt), partial (teilweise), no (nicht erfüllt),
na (nicht anwendbar, wird aus der Wertung genommen).

Score = Summe(Gewicht * Faktor) / Summe(Gewicht) * 100 über alle anwendbaren Parameter.
Ampel:
  rot    - ein K.O.-Parameter ist "nicht erfüllt" ODER Score < Gelb-Schwelle
  gelb   - Score < Grün-Schwelle ODER ein K.O.-Parameter ist nur "teilweise" erfüllt
  grün   - sonst
  grau   - noch nichts bewertet
"""
from collections import OrderedDict

FACTORS = {"yes": 1.0, "partial": 0.5, "no": 0.0}
ANSWERS = ("yes", "partial", "no", "na")
PRIORITY_ORDER = ["critical", "high", "medium", "low"]


def _priority(item) -> str:
    if item.is_blocker and item.answer == "no":
        return "critical"
    if item.is_blocker or item.weight >= 7:
        return "high"
    if item.weight >= 4:
        return "medium"
    return "low"


def _score(items) -> float | None:
    rated = [i for i in items if i.answer in FACTORS]
    total = sum(i.weight for i in rated)
    if not total:
        return None
    return sum(i.weight * FACTORS[i.answer] for i in rated) / total * 100


def evaluate(items, green_min: float, yellow_min: float) -> dict:
    items = list(items)
    score = _score(items)
    blocker_fail = [i for i in items if i.is_blocker and i.answer == "no"]
    blocker_partial = [i for i in items if i.is_blocker and i.answer == "partial"]

    if score is None:
        light = "grey"
    elif blocker_fail or score < yellow_min:
        light = "red"
    elif score < green_min or blocker_partial:
        light = "yellow"
    else:
        light = "green"

    categories: "OrderedDict[str, list]" = OrderedDict()
    for i in items:
        categories.setdefault(getattr(i, "section", i.category), []).append(i)
    category_scores = [
        {
            "name": name,
            "score": _score(group),
            "answered": sum(1 for i in group if i.answer is not None),
            "total": len(group),
        }
        for name, group in categories.items()
    ]

    findings = []
    for i in items:
        if i.answer in ("no", "partial"):
            gap = i.weight * (1 - FACTORS[i.answer])
            findings.append({
                "item_id": i.id,
                "category": getattr(i, "section", i.category),
                "name": i.name,
                "answer": i.answer,
                "weight": i.weight,
                "is_blocker": i.is_blocker,
                "priority": _priority(i),
                "gap": gap,
                "recommendation": i.recommendation,
                "comment": i.comment,
            })
    findings.sort(key=lambda f: (PRIORITY_ORDER.index(f["priority"]), -f["gap"], f["item_id"] or 0))

    answered = sum(1 for i in items if i.answer is not None)
    return {
        "score": score,
        "light": light,
        "answered": answered,
        "total": len(items),
        "complete": answered == len(items) and len(items) > 0,
        "blocker_failed": [i.name for i in blocker_fail],
        "blocker_partial": [i.name for i in blocker_partial],
        "categories": category_scores,
        "findings": findings,
    }
