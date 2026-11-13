"""Ranking, thin-data refusal, card JSON and re-check. See SPEC.md sections 3-4."""
from __future__ import annotations

from collections import defaultdict

from onefix.detectors import isolated_opening_death, untraded_death
from onefix.models import Match

DETECTORS = {d.NAME: d for d in (isolated_opening_death, untraded_death)}

MIN_SIDE_ROUNDS = 30
MIN_PATTERN_ROUNDS = 4
MIN_PATTERN_MATCHES = 2
MIN_RECHECK_ROUNDS = 20
EVIDENCE_LIMIT = 3
METRIC_WINDOW_MATCHES = 3


def _pct(wins: int, total: int) -> float:
    return round(100.0 * wins / total, 1) if total else 0.0


def _rate(fired: int, rounds: int) -> float:
    return round(100.0 * fired / rounds, 1) if rounds else 0.0


def find_candidates(matches: list[Match], steamid: str) -> dict[tuple[str, str], list[dict]]:
    """All patterns that pass the minimum sample, per (map, side), best first."""
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for det in DETECTORS.values():
        events = defaultdict(list)
        compare = defaultdict(list)  # (map, side) -> [(match_id, round, won)]
        for m in matches:
            for e in det.find_events(m, steamid):
                events[(e.map, e.side, e.place)].append(e)
            for r in m.rounds:
                if det.comparison_round(r, steamid):
                    compare[(m.map, r.side)].append((m.match_id, r.num, r.won))
        for (map_, side, place), es in events.items():
            fired = len(es)
            if fired < MIN_PATTERN_ROUNDS or len({e.match_id for e in es}) < MIN_PATTERN_MATCHES:
                continue
            fired_keys = {(e.match_id, e.round) for e in es}
            others = [w for (mid, num, w) in compare[(map_, side)] if (mid, num) not in fired_keys]
            if not others:
                continue
            fired_wins = sum(e.won for e in es)
            rounds_cost = fired * (sum(others) / len(others) - fired_wins / fired)
            if rounds_cost <= 0:
                continue
            out[(map_, side)].append(
                {"detector": det.NAME, "place": place, "events": es, "fired": fired,
                 "fired_wins": fired_wins, "other": len(others), "other_wins": sum(others),
                 "rounds_cost": rounds_cost}
            )
    for cs in out.values():
        cs.sort(key=lambda c: (-c["rounds_cost"], -c["fired"], c["detector"], c["place"]))
    return out


def build_cards(matches: list[Match], steamid: str) -> list[dict]:
    """One card per (map, side) cell, sorted by map then side."""
    side_rounds: dict[tuple[str, str], int] = defaultdict(int)
    for m in matches:
        for r in m.rounds:
            side_rounds[(m.map, r.side)] += 1
    candidates = find_candidates(matches, steamid)

    cards = []
    for (map_, side) in sorted(side_rounds):
        n = side_rounds[(map_, side)]
        base = {"map": map_, "side": side, "side_rounds": n}
        if n < MIN_SIDE_ROUNDS:
            cards.append({**base, "status": "insufficient_data",
                          "reason": f"{n} rounds played; need {MIN_SIDE_ROUNDS}.",
                          "rounds_needed": MIN_SIDE_ROUNDS - n})
        elif not candidates[(map_, side)]:
            cards.append({**base, "status": "no_fix_found"})
        else:
            cards.append({**base, **_fix_card(map_, side, n, candidates[(map_, side)][0])})
    return cards


def _fix_card(map_: str, side: str, n: int, c: dict) -> dict:
    det = DETECTORS[c["detector"]]
    wr_fired = _pct(c["fired_wins"], c["fired"])
    wr_other = _pct(c["other_wins"], c["other"])
    baseline = _rate(c["fired"], n)
    recent = sorted(c["events"], key=lambda e: (e.date, e.match_id, e.round), reverse=True)
    fill = dict(map=map_, side=side, place=c["place"], fired=c["fired"], side_rounds=n,
                wr_fired=wr_fired, wr_other=wr_other, window=METRIC_WINDOW_MATCHES,
                comparison=det.COMPARISON)
    return {
        "status": "fix",
        "detector": det.NAME,
        "place": c["place"],
        "fix_text": det.FIX_TEMPLATE.format(**fill),
        "drill": det.DRILL_TEMPLATE.format(**fill),
        "evidence": [
            {"match_id": e.match_id, "round": e.round, "t": e.t, "place": e.place}
            for e in recent[:EVIDENCE_LIMIT]
        ],
        "metric": {
            "name": det.METRIC_NAME,
            "baseline": baseline,
            "target": round(baseline / 2, 1),
            "window_matches": METRIC_WINDOW_MATCHES,
        },
        "stats": {
            "fired_rounds": c["fired"],
            "matches_with_pattern": len({e.match_id for e in c["events"]}),
            "win_rate_fired_pct": wr_fired,
            "win_rate_other_pct": wr_other,
            "comparison_rounds": c["other"],
            "rounds_cost": round(c["rounds_cost"], 2),
            "note": "Observed difference for this player, not a causal estimate.",
        },
    }


def recheck(card: dict, new_matches: list[Match], steamid: str) -> dict:
    """Re-measure a fix card's metric on newer matches."""
    if card.get("status") != "fix":
        raise ValueError("recheck needs a card with status 'fix'")
    det = DETECTORS[card["detector"]]
    rounds = fired = 0
    for m in new_matches:
        if m.map != card["map"]:
            continue
        rounds += sum(1 for r in m.rounds if r.side == card["side"])
        fired += sum(
            1 for e in det.find_events(m, steamid)
            if e.side == card["side"] and e.place == card["place"]
        )
    out = {"map": card["map"], "side": card["side"], "place": card["place"],
           "side_rounds": rounds, "fired_rounds": fired}
    if rounds < MIN_RECHECK_ROUNDS:
        return {**out, "status": "insufficient_data",
                "reason": f"{rounds} rounds played; need {MIN_RECHECK_ROUNDS}."}
    rate = _rate(fired, rounds)
    m = card["metric"]
    status = "fixed" if rate <= m["target"] else "improving" if rate < m["baseline"] else "no_change"
    return {**out, "status": status, "rate": rate,
            "baseline": m["baseline"], "target": m["target"]}
