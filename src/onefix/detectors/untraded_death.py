"""Detector: untraded_death. See SPEC.md section 2b. Deterministic; no I/O."""
from __future__ import annotations

from onefix.detectors.common import TRADE_WINDOW, Event, is_enemy_kill, outnumbered, was_traded
from onefix.models import Kill, Match, Round

__all__ = ["TRADE_WINDOW", "Event", "fires", "find_events", "comparison_round"]

NAME = "untraded_death"

METRIC_NAME = "untraded_deaths_per_100_side_rounds"
COMPARISON = "the other rounds you died in before your team was outnumbered"
FIX_TEMPLATE = (
    "On {map} {side} side you died at {place} without being traded in {fired} of "
    "{side_rounds} rounds, while your team was not yet outnumbered. Your team won "
    "{wr_fired}% of those rounds and {wr_other}% of {comparison}. Before you "
    "take a fight at {place}, make sure a teammate is set up to trade you, or "
    "fight from a spot you can fall back from."
)
DRILL_TEMPLATE = (
    "For your next {window} {map} games: each time you are about to fight at "
    "{place}, call it and check a teammate can see the angle you are fighting. "
    "If nobody can, give the spot up and reposition."
)


def _my_death(rnd: Round, steamid: str) -> Kill | None:
    for k in sorted(rnd.kills, key=lambda k: k.t):
        if k.victim == steamid and k.t >= 0:
            return k
    return None


def comparison_round(rnd: Round, steamid: str) -> bool:
    """Like for like: rounds where the player died before their team was outnumbered.

    Deaths in already-outnumbered rounds are excluded from both sides of the comparison:
    those rounds are nearly always lost, whatever the player did."""
    death = _my_death(rnd, steamid)
    return death is not None and not outnumbered(rnd, death)


def fires(rnd: Round, steamid: str) -> Kill | None:
    death = _my_death(rnd, steamid)
    if death is None:
        return None
    if not is_enemy_kill(death):
        return None  # suicide, fall, bomb or team kill
    if not death.victim_teammates_alive:
        return None  # last alive: nobody could trade
    if outnumbered(rnd, death):
        return None  # round already going badly: not evidence of a habit
    if was_traded(rnd, death):
        return None
    return death


def find_events(match: Match, steamid: str) -> list[Event]:
    events = []
    for rnd in match.rounds:
        death = fires(rnd, steamid)
        if death is not None:
            events.append(Event(match.match_id, match.date, match.map, rnd.side,
                                rnd.num, death.t, death.place, rnd.won))
    return events
