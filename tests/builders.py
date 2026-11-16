"""Synthetic match builders. Not real demo data."""
ME, MATE, ENEMY = "me", "mate", "enemy"
# Four living teammates (a full team of 5), so deaths are not "outnumbered" by default.
FAR = [[5000, 0, 0], [5200, 0, 0], [5400, 0, 0], [5600, 0, 0]]
NEAR = [[300, 0, 0], [5200, 0, 0], [5400, 0, 0], [5600, 0, 0]]


def other(side):
    return "CT" if side == "T" else "T"


def death(t=20.0, victim=ME, attacker=ENEMY, side="T", place="Palace", mates=FAR,
          attacker_side=None, pos=(0, 0, 0), me_pos=None, me_place=None):
    """`side` is the victim's side; the attacker is on the other side unless given.
    `me_pos` / `me_place`: where the analysed player stood at this kill (None = not known)."""
    return {"t": t, "attacker": attacker, "victim": victim, "victim_side": side,
            "attacker_side": attacker_side or other(side),
            "place": place, "pos": list(pos), "victim_teammates_alive": mates,
            "player_pos": list(me_pos) if me_pos is not None else None,
            "player_place": me_place}


def rnd(num, side="T", won=True, kills=()):
    return {"num": num, "side": side, "won": won, "kills": list(kills)}


def match(match_id, rounds, map_="de_mirage", date="2026-11-01"):
    return {"match_id": match_id, "map": map_, "date": date, "rounds": rounds}


def half(match_id, n=12, iso_rounds=(), place="Palace", side="T", date="2026-11-01",
         map_="de_mirage", clean_won=True):
    """n rounds on one side. Rounds in iso_rounds are lost isolated opening deaths."""
    rounds = []
    for i in range(1, n + 1):
        if i in iso_rounds:
            rounds.append(rnd(i, side, False, [death(side=side, place=place)]))
        else:
            rounds.append(rnd(i, side, clean_won))
    return match(match_id, rounds, map_, date)
