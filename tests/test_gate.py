"""Confidence gate: Fisher exact p-value + Bonferroni over patterns tested per cell."""
from math import comb

import pytest

from builders import ENEMY, MATE, ME, NEAR, death, match, rnd
from onefix import cards
from onefix.models import match_from_dict


def test_fisher_matches_hand_computed_value():
    # 0 wins in 4 fired rounds; 8 wins in 24 others. P = C(20,4) / C(28,4).
    assert cards.fisher_lower_p(0, 4, 8, 24) == pytest.approx(comb(20, 4) / comb(28, 4))
    assert cards.fisher_lower_p(0, 4, 8, 24) == pytest.approx(0.2366, abs=1e-4)


def test_fisher_is_one_when_fired_rounds_won_everything():
    assert cards.fisher_lower_p(4, 4, 3, 20) == pytest.approx(1.0)


def test_fisher_is_small_when_fired_lost_and_others_won():
    assert cards.fisher_lower_p(0, 5, 31, 31) == pytest.approx(1 / comb(36, 5))


def _c(place, cost, p, detector="untraded_death", fired=4):
    return {"detector": detector, "place": place, "rounds_cost": cost, "p_value": p,
            "fired": fired}


def test_bonferroni_threshold_shrinks_with_patterns_tested():
    alone, threshold = cards.pick_fix([_c("Palace", 2.0, 0.03)])
    assert alone["place"] == "Palace" and threshold == cards.ALPHA
    crowded, threshold = cards.pick_fix([_c("Palace", 2.0, 0.03), _c("Apps", -1.0, 0.9)])
    assert crowded is None and threshold == cards.ALPHA / 2


def test_gate_picks_highest_cost_among_passing_not_lowest_p():
    tested = [_c("A", 1.0, 0.0001), _c("B", 3.0, 0.01), _c("C", 5.0, 0.2)]
    best, _ = cards.pick_fix(tested)
    assert best["place"] == "B"


def test_no_observed_cost_never_passes_even_with_tiny_p():
    assert cards.pick_fix([_c("A", 0.0, 0.0)])[0] is None


def _real_like():
    """Mirrors the T/PalaceInterior pattern on Brandon's demos: 0 of 4 untraded Palace
    death rounds won, 8 of 24 other death rounds won. 36 T rounds over 3 matches."""
    plan = {  # match -> list of (kind, won); kinds: palace, traded, survived
        "m1": [("palace", False)] * 2 + [("traded", True)] * 3 + [("traded", False)] * 5
              + [("survived", True)] * 2,
        "m2": [("palace", False)] * 2 + [("traded", True)] * 3 + [("traded", False)] * 5
              + [("survived", True)] * 2,
        "m3": [("traded", True)] * 2 + [("traded", False)] * 6 + [("survived", True)] * 4,
    }
    trade = death(t=21.0, victim=ENEMY, attacker=MATE, side="CT")
    ms = []
    for i, (mid, rows) in enumerate(plan.items(), start=1):
        rs = []
        for n, (kind, won) in enumerate(rows, start=1):
            if kind == "palace":
                kills = [death(place="Palace", mates=NEAR)]
            elif kind == "traded":
                kills = [death(place="Apps", mates=NEAR), trade]
            else:
                kills = []
            rs.append(rnd(n, "T", won, kills))
        ms.append(match_from_dict(match(mid, rs, date=f"2026-11-0{i}")))
    return ms


def test_real_data_style_pattern_is_refused_as_chance():
    (card,) = cards.build_cards(_real_like(), ME)
    assert card["status"] == "no_fix_found"
    assert card["patterns_tested"] == 1
    assert "smallest p = 0.237" in card["reason"]
    assert "needed <= 0.05" in card["reason"]


def test_fix_card_reports_gate_stats():
    ms = [match_from_dict(m) for m in (
        match(f"m{i}", [rnd(n, "T", n > 2, [death()] if n <= 2 else []) for n in range(1, 13)],
              date=f"2026-11-0{i}")
        for i in (1, 2, 3))]
    (card,) = cards.build_cards(ms, ME)
    assert card["status"] == "fix"
    assert card["stats"]["p_value"] < card["stats"]["p_threshold"]
    assert card["stats"]["patterns_tested"] >= 1


def test_no_pattern_reason():
    ms = [match_from_dict(match(f"m{i}", [rnd(n, "T", True) for n in range(1, 13)]))
          for i in (1, 2, 3)]
    (card,) = cards.build_cards(ms, ME)
    assert card["status"] == "no_fix_found" and card["patterns_tested"] == 0
