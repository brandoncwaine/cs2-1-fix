from builders import ENEMY, MATE, ME, NEAR, death, match, rnd
from onefix.detectors import isolated_opening_death as iod
from onefix.models import match_from_dict


def events(rounds):
    return iod.find_events(match_from_dict(match("m", rounds)), ME)


def test_fires_on_isolated_untraded_opening_death():
    ev = events([rnd(1, kills=[death()])])
    assert [(e.round, e.place) for e in ev] == [(1, "Palace")]


def test_not_isolated_when_teammate_in_range():
    assert events([rnd(1, kills=[death(mates=NEAR)])]) == []


def test_boundary_distance_is_not_isolated():
    assert events([rnd(1, kills=[death(mates=[[iod.ISOLATION_DISTANCE, 0, 0]])])]) == []


def test_traded_death_excluded():
    trade = death(t=23.0, victim=ENEMY, attacker=MATE, side="CT")
    assert events([rnd(1, kills=[death(t=20.0), trade])]) == []


def test_late_trade_does_not_count():
    late = death(t=20.0 + iod.TRADE_WINDOW + 0.1, victim=ENEMY, attacker=MATE, side="CT")
    assert len(events([rnd(1, kills=[death(t=20.0), late])])) == 1


def test_not_opening_death_when_teammate_died_first():
    first = death(t=10.0, victim=MATE)
    assert events([rnd(1, kills=[first, death(t=20.0)])]) == []


def test_enemy_dying_first_does_not_block():
    enemy_first = death(t=5.0, victim=ENEMY, attacker=MATE, side="CT")
    assert len(events([rnd(1, kills=[enemy_first, death(t=20.0)])])) == 1


def test_kill_order_in_file_does_not_matter():
    first = death(t=10.0, victim=MATE)
    assert events([rnd(1, kills=[death(t=20.0), first])]) == []


def test_other_players_death_ignored():
    assert events([rnd(1, kills=[death(victim=MATE)])]) == []


def test_missing_place_becomes_unknown():
    assert events([rnd(1, kills=[death(place=None)])])[0].place == "unknown"


def test_suicide_world_and_team_kill_opening_deaths_excluded():
    assert events([rnd(1, kills=[death(attacker="world")])]) == []
    assert events([rnd(1, kills=[death(attacker=ME, attacker_side="T")])]) == []
    assert events([rnd(1, kills=[death(attacker=MATE, attacker_side="T")])]) == []


def test_killer_dying_to_own_team_or_world_is_not_a_trade():
    for not_trade in (
        death(t=22.0, victim=ENEMY, attacker="enemy2", side="CT", attacker_side="CT"),
        death(t=22.0, victim=ENEMY, attacker="world", side="CT", attacker_side=None),
        death(t=22.0, victim=ENEMY, attacker=ENEMY, side="CT", attacker_side="CT"),
    ):
        assert len(events([rnd(1, kills=[death(t=20.0), not_trade])])) == 1


def test_kill_without_attacker_side_never_counts_as_trade():
    trade = {**death(t=22.0, victim=ENEMY, attacker=MATE, side="CT"), "attacker_side": None}
    assert len(events([rnd(1, kills=[death(t=20.0), trade])])) == 1
