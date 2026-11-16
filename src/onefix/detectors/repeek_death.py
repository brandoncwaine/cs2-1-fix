"""Detector: repeek_death. See SPEC.md section 2e. Deterministic; no I/O."""
from __future__ import annotations

import math

from onefix.detectors.common import Event, is_enemy_kill, outnumbered
from onefix.models import Kill, Match, Round

NAME = "repeek_death"

# Provisional thresholds. Not yet validated against real demos.
REPEEK_WINDOW = 5.0  # seconds between the player's kill and their death
REPEEK_DISTANCE = 250.0  # game units: died this close to where they got the kill

METRIC_NAME = "repeek_deaths_per_100_side_rounds"
COMPARISON = "the other rounds where you got a kill and died later"
ADVICE_TEMPLATE = "After a kill at {place}, move: the enemy team now knows exactly where you are."
FIX_TEMPLATE = (
    "On {map} {side} side, in {fired} of {side_rounds} rounds you got a kill at {place} "
    "and then died in the same spot within a few seconds. Your team won {wr_fired}% of "
    "those rounds and {wr_other}% of {comparison}. "
) + ADVICE_TEMPLATE
DRILL_TEMPLATE = (
    "For your next {window} {map} games: after every kill at {place}, get behind "
    "cover or change position before you look at the same angle again."
)


def _my_death(rnd: Round, steamid: str) -> Kill | None:
    """The player's death, if it is an enemy kill while their team was not outnumbered."""
    for k in sorted(rnd.kills, key=lambda k: k.t):
        if k.victim == steamid and k.t >= 0:
            return k if is_enemy_kill(k) and not outnumbered(rnd, k) else None
    return None


def _my_kills_before(rnd: Round, steamid: str, death: Kill) -> list[Kill]:
    """The player's enemy kills before their death, where their position is known."""
    return [k for k in sorted(rnd.kills, key=lambda k: k.t)
            if k.attacker == steamid and is_enemy_kill(k) and k.player_pos is not None
            and 0 <= k.t < death.t]


def comparison_round(rnd: Round, steamid: str) -> bool:
    """Like for like: rounds where the player got a kill and then died, not outnumbered."""
    death = _my_death(rnd, steamid)
    return death is not None and bool(_my_kills_before(rnd, steamid, death))


def fires(rnd: Round, steamid: str) -> Kill | None:
    """The player's kill that they then died next to, else None."""
    death = _my_death(rnd, steamid)
    if death is None:
        return None
    for k in reversed(_my_kills_before(rnd, steamid, death)):
        if (death.t - k.t <= REPEEK_WINDOW
                and math.dist(k.player_pos, death.pos) <= REPEEK_DISTANCE):
            return k
    return None


def find_events(match: Match, steamid: str) -> list[Event]:
    events = []
    for rnd in match.rounds:
        k = fires(rnd, steamid)
        if k is not None:
            events.append(Event(match.match_id, match.date, match.map, rnd.side,
                                rnd.num, k.t, k.player_place or "unknown", rnd.won))
    return events
