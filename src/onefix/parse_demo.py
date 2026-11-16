"""Adapter: CS2 .dem -> normalised match dict (SPEC.md section 1). Needs demoparser2.

Usage: python -m onefix.parse_demo --steamid <id> --out <dir> demo1.dem demo2.dem ...
"""
from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from pathlib import Path

from onefix.models import SCHEMA

TICKRATE = 64.0
SIDES = {"TERRORIST": "T", "CT": "CT"}


def demo_to_match(path: str | Path, steamid: str) -> dict:
    from demoparser2 import DemoParser

    path = Path(path)
    p = DemoParser(str(path))
    map_ = p.parse_header()["map_name"]
    freeze = sorted(int(t) for t in p.parse_event("round_freeze_end")["tick"])
    ends = p.parse_event("round_end").sort_values("tick")
    deaths = p.parse_event(
        "player_death", player=["X", "Y", "Z", "last_place_name", "team_name"]
    ).sort_values("tick")

    # Each round = (last freeze end before the round end, round end).
    spans = []
    for _, e in ends.iterrows():
        i = bisect_right(freeze, int(e["tick"])) - 1
        if i < 0 or e["winner"] not in ("T", "CT"):
            continue
        if spans and spans[-1][0] == freeze[i]:
            continue  # duplicate round_end for the same round
        spans.append((freeze[i], int(e["tick"]), e["winner"]))

    in_round = deaths[[any(s <= t <= e for s, e, _ in spans) for t in deaths["tick"]]]
    wanted = sorted({s for s, _, _ in spans} | {int(t) for t in in_round["tick"]})
    ticks = p.parse_ticks(["X", "Y", "Z", "is_alive", "team_name", "last_place_name"], ticks=wanted)
    ticks["steamid"] = ticks["steamid"].astype(str)
    by_tick = {int(t): g for t, g in ticks.groupby("tick")}

    rounds = []
    for num, (start, end, winner) in enumerate(spans, start=1):
        me = by_tick[start][by_tick[start]["steamid"] == steamid]
        if me.empty or me.iloc[0]["team_name"] not in SIDES:
            continue  # player not on a team this round
        side = SIDES[me.iloc[0]["team_name"]]
        kills = []
        for _, d in in_round[(in_round["tick"] >= start) & (in_round["tick"] <= end)].iterrows():
            if d["user_team_name"] not in SIDES:
                continue
            victim = str(d["user_steamid"])
            snap = by_tick[int(d["tick"])]
            mates = snap[
                (snap["team_name"] == d["user_team_name"])
                & snap["is_alive"]
                & (snap["steamid"] != victim)
            ]
            attacker = d["attacker_steamid"]
            # The analysed player's own position, when alive and not the victim.
            own = snap[(snap["steamid"] == steamid) & snap["is_alive"]]
            own = None if own.empty or victim == steamid else own.iloc[0]
            kills.append(
                {
                    "t": round((int(d["tick"]) - start) / TICKRATE, 2),
                    "attacker": str(attacker) if attacker is not None and attacker == attacker else "world",
                    "attacker_side": SIDES.get(d["attacker_team_name"]),
                    "victim": victim,
                    "victim_side": SIDES[d["user_team_name"]],
                    "place": d["user_last_place_name"] or "unknown",
                    "pos": [round(float(d[f"user_{a}"]), 1) for a in "XYZ"],
                    "victim_teammates_alive": [
                        [round(float(m[a]), 1) for a in "XYZ"] for _, m in mates.iterrows()
                    ],
                    "player_pos": None if own is None
                    else [round(float(own[a]), 1) for a in "XYZ"],
                    "player_place": None if own is None
                    else (own["last_place_name"] or "unknown"),
                }
            )
        rounds.append({"num": num, "side": side, "won": winner == side, "kills": kills})

    # No date in the demo; match ids in the file name increase over time, so sort on those.
    return {"schema": SCHEMA, "match_id": path.stem, "map": map_, "date": "", "rounds": rounds}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steamid", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("demos", nargs="+")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for demo in args.demos:
        m = demo_to_match(demo, args.steamid)
        (out / f"{m['match_id']}.json").write_text(json.dumps(m))
        print(m["match_id"], m["map"], len(m["rounds"]), "rounds")


if __name__ == "__main__":
    main()
