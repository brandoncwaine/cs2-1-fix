"""Normalised, parser-independent match schema. See SPEC.md section 1."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

Pos = tuple[float, float, float]

# Version of the match file format. 2 added `player_pos` / `player_place` on kills.
SCHEMA = 2


@dataclass(frozen=True)
class Kill:
    t: float
    attacker: str
    victim: str
    victim_side: str
    place: str
    pos: Pos
    victim_teammates_alive: tuple[Pos, ...]
    attacker_side: str | None = None
    # The analysed player's own position and callout at this kill's tick; None when they
    # are dead, are the victim, or the file predates schema 2.
    player_pos: Pos | None = None
    player_place: str | None = None


@dataclass(frozen=True)
class Round:
    num: int
    side: str
    won: bool
    kills: tuple[Kill, ...]


@dataclass(frozen=True)
class Match:
    match_id: str
    map: str
    date: str
    rounds: tuple[Round, ...]


def _pos(raw) -> Pos:
    x, y, z = raw
    return (float(x), float(y), float(z))


def match_from_dict(d: dict) -> Match:
    rounds = []
    for r in d["rounds"]:
        if r["side"] not in ("T", "CT"):
            raise ValueError(f"bad side {r['side']!r} in round {r['num']}")
        kills = tuple(
            Kill(
                t=float(k["t"]),
                attacker=str(k["attacker"]),
                victim=str(k["victim"]),
                victim_side=k["victim_side"],
                place=k.get("place") or "unknown",
                pos=_pos(k["pos"]),
                victim_teammates_alive=tuple(_pos(p) for p in k["victim_teammates_alive"]),
                attacker_side=k.get("attacker_side"),
                player_pos=_pos(k["player_pos"]) if k.get("player_pos") else None,
                player_place=(k.get("player_place") or "unknown") if k.get("player_pos") else None,
            )
            for k in r["kills"]
        )
        rounds.append(Round(num=int(r["num"]), side=r["side"], won=bool(r["won"]), kills=kills))
    return Match(match_id=str(d["match_id"]), map=d["map"], date=d["date"], rounds=tuple(rounds))


def load_match(path: str | Path) -> Match:
    return match_from_dict(json.loads(Path(path).read_text()))
