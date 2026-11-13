"""Detector: untraded_death. See SPEC.md section 2b. Deterministic; no I/O."""
from __future__ import annotations

from onefix.detectors.isolated_opening_death import Event
from onefix.models import Kill, Match, Round

NAME = "untraded_death"

# Provisional threshold. Not yet validated against real demos.
TRADE_WINDOW = 5.0  # seconds

METRIC_NAME = "untraded_deaths_per_100_side_rounds"
COMPARISON = "the other rounds you died in"
FIX_TEMPLATE = (
    "On {map} {side} side you died at {place} without being traded in {fired} of "
    "{side_rounds} rounds, while teammates were still alive. Your team won "
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
    """Compare only against rounds where the player also died."""
    return _my_death(rnd, steamid) is not None


def fires(rnd: Round, steamid: str) -> Kill | None:
    death = _my_death(rnd, steamid)
    if death is None:
        return None
    if death.attacker in ("world", steamid) or death.attacker_side == death.victim_side:
        return None  # suicide, fall, bomb or team kill
    if not death.victim_teammates_alive:
        return None  # last alive: nobody could trade
    if any(
        k.victim == death.attacker and death.t < k.t <= death.t + TRADE_WINDOW
        for k in rnd.kills
    ):
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
