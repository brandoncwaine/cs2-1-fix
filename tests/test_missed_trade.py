from builders import ENEMY, FAR, MATE, ME, NEAR, death, match, rnd
from onefix import cards
from onefix.detectors import missed_trade as mt
from onefix.models import match_from_dict

CLOSE = (300, 0, 0)  # 300 units from the teammate, who dies at the origin


def mate_death(t=20.0, me_pos=CLOSE, **kw):
    return death(t=t, victim=MATE, me_pos=me_pos, me_place="Jungle", **kw)


def events(rounds):
    return mt.find_events(match_from_dict(match("m", rounds)), ME)


def test_fires_when_teammate_dies_next_to_me_and_nobody_trades():
    (e,) = events([rnd(1, kills=[mate_death()])])
    assert (e.place, e.t) == ("Jungle", 20.0)  # where I stood, when the teammate died


def test_no_event_when_i_trade_or_another_teammate_does():
    for trader in (ME, "mate2"):
        trade = death(t=22.0, victim=ENEMY, attacker=trader, side="CT")
        r = rnd(1, kills=[mate_death(), trade])
        assert events([r]) == []
        assert mt.comparison_round(match_from_dict(match("m", [r])).rounds[0], ME)


def test_late_trade_still_fires():
    late = death(t=25.01, victim=ENEMY, attacker=ME, side="CT")
    assert len(events([rnd(1, kills=[mate_death(), late])])) == 1


def test_out_of_range_or_unknown_position_is_no_chance():
    for pos in ((901, 0, 0), None):
        r = rnd(1, kills=[mate_death(me_pos=pos)])
        assert events([r]) == []
        assert not mt.comparison_round(match_from_dict(match("m", [r])).rounds[0], ME)
    assert len(events([rnd(1, kills=[mate_death(me_pos=(900, 0, 0))])])) == 1  # boundary is in range


def test_no_chance_when_i_die_inside_the_trade_window():
    assert events([rnd(1, kills=[mate_death(), death(t=23.0)])]) == []
    assert len(events([rnd(1, kills=[mate_death(), death(t=25.5)])])) == 1


def test_no_chance_when_team_is_outnumbered():
    assert events([rnd(1, kills=[mate_death(mates=NEAR[:2])])]) == []  # 3 alive against 5


def test_teammate_dying_to_world_or_team_is_no_chance():
    assert events([rnd(1, kills=[mate_death(attacker="world")])]) == []
    assert events([rnd(1, kills=[mate_death(attacker=ME, attacker_side="T")])]) == []


def test_enemy_deaths_and_my_own_death_are_ignored():
    enemy_dies = death(victim=ENEMY, attacker=MATE, side="CT", me_pos=CLOSE, me_place="Jungle")
    assert events([rnd(1, kills=[enemy_dies])]) == []
    assert events([rnd(1, kills=[death(me_pos=None)])]) == []


def test_one_event_per_round_the_first_untraded_chance():
    traded = mate_death(t=10.0)
    trade = death(t=11.0, victim=ENEMY, attacker=ME, side="CT")
    missed = death(t=30.0, victim="mate2", attacker="enemy2", me_pos=CLOSE, me_place="Stairs",
                   mates=FAR[:3])
    missed_again = death(t=40.0, victim="mate3", attacker="enemy2", me_pos=CLOSE,
                         me_place="Stairs", mates=FAR[:2])
    (e,) = events([rnd(1, kills=[missed_again, missed, trade, traded])])
    assert (e.t, e.place) == (30.0, "Stairs")


def test_card_compares_against_other_rounds_with_a_chance_to_trade():
    ms = []
    for i in (1, 2, 3):
        rs = []
        for n in range(1, 13):
            if n <= 2:  # missed, lost
                rs.append(rnd(n, "T", False, [mate_death()]))
            elif n <= 6:  # traded, won
                trade = death(t=21.0, victim=ENEMY, attacker=ME, side="CT")
                rs.append(rnd(n, "T", True, [mate_death(), trade]))
            else:
                rs.append(rnd(n, "T", True))
        ms.append(match_from_dict(match(f"m{i}", rs, date=f"2026-11-0{i}")))
    (card,) = cards.build_cards(ms, ME)
    assert card["status"] == "fix"
    assert (card["detector"], card["place"]) == ("missed_trade", "Jungle")
    assert card["stats"]["fired_rounds"] == 6
    assert card["stats"]["comparison_rounds"] == 12  # the traded rounds, not the 18 quiet ones
    assert "while you were at Jungle" in card["fix_text"]
