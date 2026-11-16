from builders import ENEMY, FAR, MATE, ME, death, match, rnd
from onefix import cards
from onefix.detectors import repeek_death as rd
from onefix.models import match_from_dict

SPOT = (1000, 0, 0)


def my_kill(t=20.0, me_pos=SPOT, victim=ENEMY, **kw):
    return death(t=t, victim=victim, attacker=ME, side="CT", me_pos=me_pos, me_place="Window", **kw)


def my_death(t=23.0, pos=SPOT, attacker="enemy2", **kw):
    return death(t=t, attacker=attacker, pos=pos, place="Window", **kw)


def events(rounds):
    return rd.find_events(match_from_dict(match("m", rounds)), ME)


def compared(r):
    return rd.comparison_round(match_from_dict(match("m", [r])).rounds[0], ME)


def test_fires_when_i_die_where_i_just_got_a_kill():
    (e,) = events([rnd(1, kills=[my_death(), my_kill()])])
    assert (e.place, e.t) == ("Window", 20.0)  # the kill, not the death


def test_time_and_distance_boundaries():
    assert len(events([rnd(1, kills=[my_kill(), my_death(t=25.0)])])) == 1
    assert events([rnd(1, kills=[my_kill(), my_death(t=25.01)])]) == []
    assert len(events([rnd(1, kills=[my_kill(), my_death(pos=(1250, 0, 0))])])) == 1
    assert events([rnd(1, kills=[my_kill(), my_death(pos=(1251, 0, 0))])]) == []


def test_moving_away_or_waiting_is_a_comparison_round_not_an_event():
    for r in (rnd(1, kills=[my_kill(), my_death(pos=(2000, 0, 0))]),
              rnd(1, kills=[my_kill(), my_death(t=40.0)])):
        assert events([r]) == [] and compared(r)


def test_rounds_without_a_kill_or_without_a_death_are_not_compared():
    for r in (rnd(1, kills=[my_death()]), rnd(1, kills=[my_kill()]), rnd(1)):
        assert events([r]) == [] and not compared(r)


def test_kill_after_my_death_or_with_unknown_position_does_not_count():
    assert events([rnd(1, kills=[my_death(t=19.0), my_kill()])]) == []
    r = rnd(1, kills=[my_kill(me_pos=None), my_death()])
    assert events([r]) == [] and not compared(r)


def test_team_kill_by_me_is_not_a_kill():
    tk = death(t=20.0, victim="mate", attacker=ME, attacker_side="T", me_pos=SPOT)
    assert events([rnd(1, kills=[tk, my_death()])]) == []


def test_death_to_world_or_when_outnumbered_is_excluded():
    assert events([rnd(1, kills=[my_kill(), my_death(attacker="world")])]) == []
    r = rnd(1, kills=[my_kill(), my_death(mates=FAR[:2])])  # 3 alive against 4
    assert events([r]) == [] and not compared(r)


def test_uses_the_latest_kill_before_the_death():
    early = my_kill(t=5.0, me_pos=(4000, 0, 0))
    (e,) = events([rnd(1, kills=[early, my_kill(t=20.0, victim="enemy3"), my_death()])])
    assert e.t == 20.0


def test_card_compares_against_other_kill_then_death_rounds():
    ms = []
    for i in (1, 2, 3):
        rs = []
        for n in range(1, 13):
            # Every death is traded, so the other death detectors stay quiet.
            if n <= 2:  # stayed and died, lost
                trade = death(t=24.0, victim="enemy2", attacker=MATE, side="CT")
                rs.append(rnd(n, "T", False, [my_kill(), my_death(), trade]))
            elif n <= 6:  # moved, died later, won
                trade = death(t=51.0, victim="enemy2", attacker=MATE, side="CT")
                rs.append(rnd(n, "T", True, [my_kill(), my_death(t=50.0, pos=(3000, 0, 0)), trade]))
            else:
                rs.append(rnd(n, "T", True))
        ms.append(match_from_dict(match(f"m{i}", rs, date=f"2026-11-0{i}")))
    (card,) = cards.build_cards(ms, ME)
    assert card["status"] == "fix"
    assert (card["detector"], card["place"]) == ("repeek_death", "Window")
    assert card["stats"]["fired_rounds"] == 6
    assert card["stats"]["comparison_rounds"] == 12
