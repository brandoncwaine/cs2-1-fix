"""Detector: isolated_opening_death. See SPEC.md section 2. Deterministic; no I/O."""
from __future__ import annotations

import math
from dataclasses import dataclass

from onefix.models import Kill, Match, Round

NAME = "isolated_opening_death"

# Provisional thresholds. Not yet validated against real demos.
ISOLATION_DISTANCE = 900.0  # game units to nearest living teammate
TRADE_WINDOW = 5.0  # seconds

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


@dataclass(frozen=True)
class Event:
    match_id: str
    date: str
    map: str
    side: str
    round: int
    t: float
    place: str
    won: bool


def _nearest_teammate(kill: Kill) -> float:
    if not kill.victim_teammates_alive:
        return math.inf
    return min(math.dist(kill.pos, p) for p in kill.victim_teammates_alive)


def _was_traded(rnd: Round, death: Kill) -> bool:
    return any(
        k.victim == death.attacker and death.t < k.t <= death.t + TRADE_WINDOW
        for k in rnd.kills
    )


def fires(rnd: Round, steamid: str) -> Kill | None:
    """Return the player's death if this round matches the trigger, else None."""
    team_deaths = sorted(
        (k for k in rnd.kills if k.victim_side == rnd.side and k.t >= 0),
        key=lambda k: k.t,
    )
    if not team_deaths or team_deaths[0].victim != steamid:
        return None
    death = team_deaths[0]
    if _nearest_teammate(death) <= ISOLATION_DISTANCE:
        return None
    if _was_traded(rnd, death):
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
