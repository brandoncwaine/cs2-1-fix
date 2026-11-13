"""Synthetic match builders. Not real demo data."""
ME, MATE, ENEMY = "me", "mate", "enemy"
FAR = [[5000, 0, 0]]
NEAR = [[300, 0, 0]]


def death(t=20.0, victim=ME, attacker=ENEMY, side="T", place="Palace", mates=FAR):
    return {"t": t, "attacker": attacker, "victim": victim, "victim_side": side,
            "place": place, "pos": [0, 0, 0], "victim_teammates_alive": mates}


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
