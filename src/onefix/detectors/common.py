"""Shared detector pieces: the Event record, enemy-kill and trade rules. Deterministic; no I/O."""
from __future__ import annotations

from dataclasses import dataclass

from onefix.models import Kill, Round

# Provisional threshold. Not yet validated against real demos.
TRADE_WINDOW = 5.0  # seconds


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


def is_enemy_kill(k: Kill) -> bool:
    """False for suicides, world damage (falls, bomb) and team kills."""
    if k.attacker in ("world", k.victim):
        return False
    return k.attacker_side != k.victim_side


def was_traded(rnd: Round, death: Kill) -> bool:
    """A teammate of the victim killed the victim's killer within TRADE_WINDOW.

    The killer's death only counts if the victim's team made it: an enemy dying to
    world damage, a team kill or their own grenade is not a trade. Needs
    `attacker_side`; a kill without it is never counted as a trade."""
    return any(
        k.victim == death.attacker
        and k.attacker_side == death.victim_side
        and k.attacker not in ("world", death.attacker)
        and death.t < k.t <= death.t + TRADE_WINDOW
        for k in rnd.kills
    )
