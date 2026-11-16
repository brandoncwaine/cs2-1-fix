"""Detector: isolated_opening_death. See SPEC.md section 2. Deterministic; no I/O."""
from __future__ import annotations

import math

from onefix.detectors.common import TRADE_RANGE, TRADE_WINDOW, Event, is_enemy_kill, was_traded
from onefix.models import Kill, Match, Round

__all__ = ["TRADE_WINDOW", "Event", "fires", "find_events", "comparison_round"]

NAME = "isolated_opening_death"

# Provisional threshold. Not yet validated against real demos.
ISOLATION_DISTANCE = TRADE_RANGE  # game units to nearest living teammate

METRIC_NAME = "isolated_opening_deaths_per_100_side_rounds"
COMPARISON = "the others"
FIX_TEMPLATE = (
    "On {map} {side} side you were the first on your team to die at {place} in "
    "{fired} of {side_rounds} rounds, with no teammate close enough to trade. "
    "Your team won {wr_fired}% of those rounds and {wr_other}% of {comparison}. "
    "Stop taking first contact at {place} alone: wait for a teammate in trade "
    "range or a flash before you peek."
)
DRILL_TEMPLATE = (
    "For your next {window} {map} games: before first contact at {place}, check "
    "the radar for a teammate in trade range. If there is none, hold the angle "
    "instead of peeking."
)


def comparison_round(rnd: Round, steamid: str) -> bool:
    """Rounds the fired rounds are compared against: all rounds."""
    return True


def _nearest_teammate(kill: Kill) -> float:
    if not kill.victim_teammates_alive:
        return math.inf
    return min(math.dist(kill.pos, p) for p in kill.victim_teammates_alive)


def fires(rnd: Round, steamid: str) -> Kill | None:
    """Return the player's death if this round matches the trigger, else None."""
    team_deaths = sorted(
        (k for k in rnd.kills if k.victim_side == rnd.side and k.t >= 0),
        key=lambda k: k.t,
    )
    if not team_deaths or team_deaths[0].victim != steamid:
        return None
    death = team_deaths[0]
    if not is_enemy_kill(death):
        return None  # suicide, fall, bomb or team kill
    if _nearest_teammate(death) <= ISOLATION_DISTANCE:
        return None
    if was_traded(rnd, death):
        return None
    return death


def find_events(match: Match, steamid: str) -> list[Event]:
    events = []
    for rnd in match.rounds:
        death = fires(rnd, steamid)
        if death is not None:
            events.append(
                Event(
                    match_id=match.match_id,
                    date=match.date,
                    map=match.map,
                    side=rnd.side,
                    round=rnd.num,
                    t=death.t,
                    place=death.place,
                    won=rnd.won,
                )
            )
    return events
