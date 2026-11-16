"""Detector: missed_trade. See SPEC.md section 2d. Deterministic; no I/O."""
from __future__ import annotations

import math

from onefix.detectors.common import (TRADE_RANGE, TRADE_WINDOW, Event, is_enemy_kill,
                                     outnumbered, was_traded)
from onefix.models import Kill, Match, Round

NAME = "missed_trade"

METRIC_NAME = "missed_trades_per_100_side_rounds"
COMPARISON = "the other rounds where a teammate died within trade range of you"
FIX_TEMPLATE = (
    "On {map} {side} side, in {fired} of {side_rounds} rounds a teammate died within "
    "trade range of you while you were at {place}, and nobody killed their killer in "
    "the next few seconds. Your team won {wr_fired}% of those rounds and {wr_other}% of "
    "{comparison}. When a teammate goes down next to you at {place}, take the fight "
    "straight away while the killer is still exposed."
)
DRILL_TEMPLATE = (
    "For your next {window} {map} games: when you play {place} with a teammate ahead "
    "of you, keep your crosshair on the angle they are fighting. If they die, swing "
    "it at once instead of backing off."
)


def _my_death_time(rnd: Round, steamid: str) -> float:
    return min((k.t for k in rnd.kills if k.victim == steamid and k.t >= 0), default=math.inf)


def _chances(rnd: Round, steamid: str) -> list[Kill]:
    """Teammate deaths the player was placed to trade, earliest first.

    A chance: a teammate dies to an enemy, the player is alive within TRADE_RANGE of them,
    the team is not outnumbered, and the player survives the trade window (a player who
    dies in it was caught in the same fight, which is a different problem)."""
    died = _my_death_time(rnd, steamid)
    out = []
    for k in sorted(rnd.kills, key=lambda k: k.t):
        if k.t < 0 or k.victim == steamid or k.victim_side != rnd.side:
            continue
        if k.player_pos is None or not is_enemy_kill(k):
            continue
        if math.dist(k.pos, k.player_pos) > TRADE_RANGE:
            continue
        if outnumbered(rnd, k) or died <= k.t + TRADE_WINDOW:
            continue
        out.append(k)
    return out


def comparison_round(rnd: Round, steamid: str) -> bool:
    """Like for like: rounds where the player had at least one chance to trade."""
    return bool(_chances(rnd, steamid))


def fires(rnd: Round, steamid: str) -> Kill | None:
    """The first chance in the round that nobody on the team converted, else None."""
    for k in _chances(rnd, steamid):
        if not was_traded(rnd, k):
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
