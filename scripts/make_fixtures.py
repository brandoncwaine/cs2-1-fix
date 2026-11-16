"""Write the sample matches in fixtures/. Made-up data, not real demos.

Run: python scripts/make_fixtures.py
See the cards: PYTHONPATH=src python -m onefix.cli --steamid me fixtures/*.json

Everything is spelled out below, so the output is the same on every run. The matches are
shaped to show all three card states with believable numbers:
  de_mirage T   fix (dying first and alone at Palace: a few rounds, most but not all lost)
  de_mirage CT  no fix found (a pattern repeats, but not strongly enough to pass the gate)
  de_inferno CT fix (dying untraded at Banana)
  de_inferno T  no fix found
  de_nuke       not enough rounds yet (one match)
The sign-in page's sample cards (src/onefix/static/login.html) are copied from this output.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "fixtures"
ME, MATE, ENEMY = "me", "mate", "enemy"

# Living teammates at the moment of a death: four far away, or one within trade range.
FAR = [[2400, 300, 0], [2600, -500, 0], [3100, 900, 0], [3300, 100, 0]]
NEAR = [[350, 120, 0], [2600, -500, 0], [3100, 900, 0], [3300, 100, 0]]

# One letter per round says what happened to the player.
#   W L  round won / lost, and the player survived or died too late to matter (no kill recorded)
#   p    died first and alone at the pattern place, untraded
#   t    died with a teammate close, and was traded
#   u    died elsewhere with a teammate close, but was not traded
#   x    died at the pattern place with a teammate close, but was not traded
# p, t, u and x are lost rounds; in upper case (P, T, U, X) the round was won anyway.
# (match id, map, date, T half, CT half, pattern place on T, pattern place on CT)
MATCHES = [
    ("sample-1", "de_mirage", "2026-11-02", "WWpLtWuLWWWt", "LWWuTWWLWpLW", "Palace", "BombsiteA"),
    ("sample-2", "de_mirage", "2026-11-04", "LpWWTLpWWWuL", "WWLLtWpWWLuW", "Palace", "BombsiteA"),
    ("sample-3", "de_mirage", "2026-11-05", "WWWtLuWWLTWL", "LuWWWPtLWWWL", "Palace", "BombsiteA"),
    ("sample-4", "de_mirage", "2026-11-08", "WWpLTWWPLuWW", "WLWpWtLWWuLW", "Palace", "BombsiteA"),
    ("sample-5", "de_mirage", "2026-11-09", "LtWpWWWuLWpW", "WWTLpWuLWWLW", "Palace", "BombsiteA"),
    ("sample-6", "de_mirage", "2026-11-12", "WpLWWtLWWuLW", "LWWtWPLWuWLW", "Palace", "BombsiteA"),
    ("sample-7", "de_inferno", "2026-11-03", "WWtLWuLWWLtW", "LWxWTWLWtWWL", "Banana", "Banana"),
    ("sample-8", "de_inferno", "2026-11-06", "LWWtWLWuWWLW", "WxLWWTWLLWTW", "Banana", "Banana"),
    ("sample-9", "de_inferno", "2026-11-07", "WLWWuLtWWLWW", "TWWLxWWtLWWU", "Banana", "Banana"),
    ("sample-10", "de_inferno", "2026-11-10", "WWLtWWLWuLWW", "WLTWWxLWWTWL", "Banana", "Banana"),
    ("sample-11", "de_inferno", "2026-11-11", "LWtWWLWWLuWW", "WWXLTWWLxWtW", "Banana", "Banana"),
    ("sample-12", "de_inferno", "2026-11-14", "WuLWWtWLWWLW", "LTWLWWLTWWuW", "Banana", "Banana"),
    ("sample-13", "de_nuke", "2026-11-15", "WWtLWuLWWLtW", "LWuWWtLWWLWL", "Outside", "Heaven"),
]

# Where and when the non-pattern deaths happen: cycled through, so no place repeats enough
# to become a pattern of its own.
ELSEWHERE = {
    "T": ["TopofMid", "Apartments", "TRamp", "Underpass", "BombsiteB", "Catwalk", "BombsiteA"],
    "CT": ["Jungle", "Window", "Market", "Connector", "BombsiteB", "Ticket", "Stairs"],
}
TIMES = [18.4, 23.1, 31.7, 15.9, 27.3, 41.2, 21.6, 36.8, 19.5, 52.4, 25.0, 33.9]


def other(side: str) -> str:
    return "CT" if side == "T" else "T"


def kill(t, attacker, victim, victim_side, place, mates) -> dict:
    return {"t": t, "attacker": attacker, "victim": victim, "victim_side": victim_side,
            "attacker_side": other(victim_side), "place": place, "pos": [0, 0, 0],
            "victim_teammates_alive": mates, "player_pos": None, "player_place": None}


def build_half(letters: str, side: str, first_num: int, pattern_place: str, counter: list[int]) -> list[dict]:
    rounds = []
    for i, letter in enumerate(letters):
        n = counter[0]
        counter[0] += 1
        t = TIMES[n % len(TIMES)]
        what = letter.lower()
        kills = []
        if what == "p":
            kills.append(kill(t, ENEMY, ME, side, pattern_place, FAR))
        elif what in "tux":
            place = pattern_place if what == "x" else ELSEWHERE[side][n % len(ELSEWHERE[side])]
            kills.append(kill(t, ENEMY, ME, side, place, NEAR))
            if what == "t":
                kills.append(kill(round(t + 1.8, 1), MATE, ENEMY, other(side), place, FAR))
        won = letter in "WPTUX"
        rounds.append({"num": first_num + i, "side": side, "won": won, "kills": kills})
    return rounds


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    counter = [0]
    for match_id, map_, date, t_half, ct_half, t_place, ct_place in MATCHES:
        rounds = (build_half(t_half, "T", 1, t_place, counter)
                  + build_half(ct_half, "CT", len(t_half) + 1, ct_place, counter))
        match = {"match_id": match_id, "map": map_, "date": date, "rounds": rounds}
        (OUT / f"{match_id}.json").write_text(json.dumps(match, indent=1) + "\n")
    print(f"wrote {len(MATCHES)} matches to {OUT}")


if __name__ == "__main__":
    main()
