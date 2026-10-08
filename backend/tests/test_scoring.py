from types import SimpleNamespace as NS

from app.scoring import evaluate


def item(weight, answer, blocker=False, name="x"):
    return NS(id=None, category="A", name=name, weight=weight, is_blocker=blocker, answer=answer,
              recommendation="", comment="")


def test_all_yes_is_green():
    r = evaluate([item(5, "yes"), item(3, "yes")], 80, 50)
    assert r["score"] == 100 and r["light"] == "green" and r["complete"]


def test_weighted_score_and_yellow():
    r = evaluate([item(8, "yes"), item(2, "no")], 90, 50)
    assert r["score"] == 80 and r["light"] == "yellow"


def test_low_score_is_red():
    assert evaluate([item(5, "no"), item(5, "partial")], 80, 50)["light"] == "red"


def test_blocker_no_forces_red_despite_high_score():
    r = evaluate([item(1, "no", blocker=True), item(10, "yes"), item(10, "yes")], 80, 50)
    assert r["score"] > 90 and r["light"] == "red" and r["blocker_failed"]


def test_blocker_partial_caps_at_yellow():
    r = evaluate([item(1, "partial", blocker=True), item(10, "yes"), item(10, "yes")], 80, 50)
    assert r["light"] == "yellow"


def test_na_is_excluded_and_unanswered_is_incomplete():
    r = evaluate([item(5, "yes"), item(9, "na"), item(5, None)], 80, 50)
    assert r["score"] == 100 and not r["complete"] and r["answered"] == 2


def test_nothing_rated_is_grey():
    assert evaluate([item(5, None)], 80, 50)["light"] == "grey"


def test_findings_sorted_by_priority():
    r = evaluate([item(3, "no", name="low"), item(5, "no", True, name="blocker"), item(8, "partial", name="high")], 80, 50)
    assert [f["name"] for f in r["findings"]] == ["blocker", "high", "low"]
