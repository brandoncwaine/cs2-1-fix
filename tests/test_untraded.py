from builders import ENEMY, MATE, ME, NEAR, death, match, rnd
from onefix import cards
from onefix.detectors import untraded_death as ud
from onefix.models import match_from_dict


def events(rounds):
    return ud.find_events(match_from_dict(match("m", rounds)), ME)


def test_fires_on_untraded_death_even_with_teammate_near_and_not_opening():
    first = death(t=5.0, victim=MATE)
    assert len(events([rnd(1, kills=[first, death(t=20.0, mates=NEAR)])])) == 1


def test_traded_death_excluded():
    trade = death(t=22.0, victim=ENEMY, attacker=MATE, side="CT")
    assert events([rnd(1, kills=[death(t=20.0), trade])]) == []


def test_last_alive_excluded():
    assert events([rnd(1, kills=[death(mates=[])])]) == []


def test_world_and_team_kills_excluded():
    assert events([rnd(1, kills=[death(attacker="world")])]) == []
    tk = {**death(attacker=MATE), "attacker_side": "T"}
    assert events([rnd(1, kills=[tk])]) == []


def test_survived_round_does_not_fire():
    assert events([rnd(1, kills=[death(victim=MATE)])]) == []


def _halves(died_other_won):
    # 3 x 12 T rounds. Rounds 1-2 of each: untraded death at Palace, lost.
    # Rounds 3-6: traded death elsewhere (comparison rounds). Rest: survived, won.
    ms = []
    for i in (1, 2, 3):
        rs = []
        for n in range(1, 13):
            if n <= 2:
                rs.append(rnd(n, "T", False, [death(mates=NEAR)]))
            elif n <= 6:
                trade = death(t=21.0, victim=ENEMY, attacker=MATE, side="CT")
                rs.append(rnd(n, "T", died_other_won, [death(place="Apps", mates=NEAR), trade]))
            else:
                rs.append(rnd(n, "T", True))
        ms.append(match_from_dict(match(f"m{i}", rs, date=f"2026-11-0{i}")))
    return ms


def test_card_compares_against_other_death_rounds_only():
    (card,) = cards.build_cards(_halves(died_other_won=True), ME)
    assert card["status"] == "fix"
    assert (card["detector"], card["place"]) == ("untraded_death", "Palace")
    assert card["stats"]["fired_rounds"] == 6
    assert card["stats"]["comparison_rounds"] == 12  # the traded-death rounds, not the 18 survived
    assert "6 of 36 rounds" in card["fix_text"]


def test_no_card_when_other_death_rounds_are_lost_too():
    # Survived rounds are all wins, but they must not count as the comparison.
    (card,) = cards.build_cards(_halves(died_other_won=False), ME)
    assert card["status"] == "no_fix_found"


def test_killer_dying_to_own_team_or_world_is_not_a_trade():
    for not_trade in (
        death(t=22.0, victim=ENEMY, attacker="enemy2", side="CT", attacker_side="CT"),
        death(t=22.0, victim=ENEMY, attacker="world", side="CT", attacker_side=None),
    ):
        assert len(events([rnd(1, kills=[death(t=20.0, mates=NEAR), not_trade])])) == 1


def test_both_detectors_share_one_trade_rule():
    from onefix.detectors import common, isolated_opening_death as iod
    assert ud.TRADE_WINDOW == iod.TRADE_WINDOW == common.TRADE_WINDOW


def _mates(n):
    return [[5000 + 200 * i, 0, 0] for i in range(n)]


def test_outnumbered_death_excluded():
    # 3 of us alive (me + 2) vs 5 of them: already losing the numbers.
    assert events([rnd(1, kills=[death(mates=_mates(2))])]) == []


def test_even_numbers_still_fire():
    # 3 v 3: two enemies died earlier, I have 2 teammates alive.
    early = [death(t=5.0 + i, victim=f"e{i}", attacker=MATE, side="CT") for i in range(2)]
    assert len(events([rnd(1, kills=early + [death(mates=_mates(2))])])) == 1


def test_one_down_is_outnumbered():
    # 4 v 5.
    assert events([rnd(1, kills=[death(mates=_mates(3))])]) == []


def test_enemy_death_at_same_instant_does_not_count_as_earlier():
    same_time = death(t=20.0, victim="e0", attacker=MATE, side="CT")
    assert events([rnd(1, kills=[same_time, death(t=20.0, mates=_mates(3))])]) == []


def test_outnumbered_rounds_are_left_out_of_comparison():
    r_out = match_from_dict(match("m", [rnd(1, kills=[death(mates=_mates(1))])])).rounds[0]
    r_even = match_from_dict(match("m", [rnd(1, kills=[death()])])).rounds[0]
    assert not ud.comparison_round(r_out, ME)
    assert ud.comparison_round(r_even, ME)
