"""Ranking, thin-data refusal, card JSON and re-check. See SPEC.md sections 3-4."""
from __future__ import annotations

from collections import defaultdict
from math import comb

from onefix.detectors import isolated_opening_death, untraded_death
from onefix.models import Match

DETECTORS = {d.NAME: d for d in (isolated_opening_death, untraded_death)}

MIN_SIDE_ROUNDS = 30
MIN_PATTERN_ROUNDS = 4
MIN_PATTERN_MATCHES = 2
MIN_RECHECK_ROUNDS = 20
EVIDENCE_LIMIT = 3
METRIC_WINDOW_MATCHES = 3
# Confidence gate (SPEC.md section 3a). Family-wise error rate per map-side cell.
ALPHA = 0.05


def _pct(wins: int, total: int) -> float:
    return round(100.0 * wins / total, 1) if total else 0.0


def _rate(fired: int, rounds: int) -> float:
    return round(100.0 * fired / rounds, 1) if rounds else 0.0


def _sig(x: float) -> float:
    return float(f"{x:.3g}")


def fisher_lower_p(fired_wins: int, fired: int, other_wins: int, other: int) -> float:
    """One-sided Fisher exact test: the chance that the fired rounds would have
    `fired_wins` or fewer wins if they were a random draw from all the rounds
    (fired + other) with the same total wins. Small p = fewer wins than chance explains."""
    total, wins = fired + other, fired_wins + other_wins
    tail = sum(comb(wins, k) * comb(total - wins, fired - k) for k in range(fired_wins + 1))
    return tail / comb(total, fired)


def pick_fix(tested: list[dict]) -> tuple[dict | None, float]:
    """Best pattern in one map-side cell that passes the confidence gate.

    `tested` is every pattern that reached the minimum sample in the cell. The
    threshold is Bonferroni-corrected by that count, because we pick the best of
    several patterns. Returns (pattern or None, threshold)."""
    if not tested:
        return None, ALPHA
    threshold = ALPHA / len(tested)
    passing = [c for c in tested if c["rounds_cost"] > 0 and c["p_value"] <= threshold]
    passing.sort(key=lambda c: (-c["rounds_cost"], -c["fired"], c["detector"], c["place"]))
    return (passing[0] if passing else None), threshold


def find_candidates(matches: list[Match], steamid: str) -> dict[tuple[str, str], list[dict]]:
    """Every pattern that reaches the minimum sample, per (map, side), highest cost first.

    Includes patterns with no observed cost: they still count as tested for the gate."""
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
            out[(map_, side)].append(
                {"detector": det.NAME, "place": place, "events": es, "fired": fired,
                 "fired_wins": fired_wins, "other": len(others), "other_wins": sum(others),
                 "rounds_cost": rounds_cost,
                 "p_value": fisher_lower_p(fired_wins, fired, sum(others), len(others))}
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
            continue
        tested = candidates[(map_, side)]
        best, threshold = pick_fix(tested)
        if best is not None:
            cards.append({**base, **_fix_card(map_, side, n, best, len(tested), threshold)})
        elif not tested:
            cards.append({**base, "status": "no_fix_found", "patterns_tested": 0,
                          "reason": f"No pattern repeated in {MIN_PATTERN_ROUNDS}+ rounds "
                                    f"across {MIN_PATTERN_MATCHES}+ matches."})
        else:
            costly = [c["p_value"] for c in tested if c["rounds_cost"] > 0]
            detail = (f"smallest p = {_sig(min(costly))}, needed <= {_sig(threshold)}"
                      if costly else "none showed fewer wins than the comparison rounds")
            cards.append({**base, "status": "no_fix_found", "patterns_tested": len(tested),
                          "reason": f"{len(tested)} pattern(s) repeated enough, but none "
                                    f"passed the confidence gate ({detail})."})
    return cards


def _fix_card(map_: str, side: str, n: int, c: dict, tested: int, threshold: float) -> dict:
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
            "p_value": _sig(c["p_value"]),
            "p_threshold": _sig(threshold),
            "patterns_tested": tested,
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
