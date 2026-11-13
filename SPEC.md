# SPEC — v0 (13 Nov 2026)

Status: first slice, built and tested on synthetic data only. All thresholds are provisional
guesses and must be checked against real demos and coach labels before anyone sees a card.

## 1. Normalised match format (parser output)

One JSON file per match, from the point of view of one player:

```json
{
  "match_id": "m1",
  "map": "de_mirage",
  "date": "2026-11-09",
  "rounds": [
    {
      "num": 1,
      "side": "T",
      "won": true,
      "kills": [
        {
          "t": 21.4,
          "attacker": "7656...A",
          "attacker_side": "CT",
          "victim": "7656...B",
          "victim_side": "T",
          "place": "PalaceInterior",
          "pos": [x, y, z],
          "victim_teammates_alive": [[x, y, z], ...]
        }
      ]
    }
  ]
}
```

- `side` and `won` are the analysed player's side and team result for that round.
- `t` is seconds since freeze time ended.
- `place` is the callout name the demo stores for the victim's position.
- `victim_teammates_alive` are positions of the victim's living teammates at the kill tick.

## 2. Detector: isolated_opening_death

- **Trigger (per round):** the player is the first death on their own team, AND the nearest
  living teammate is further than `ISOLATION_DISTANCE` (900 units), AND the killer is not
  killed by the player's team within `TRADE_WINDOW` (5 s).
- **Grouping:** by (map, side, place).
- **Minimum sample:** at least `MIN_SIDE_ROUNDS` (30) rounds in the map-side cell; the pattern
  must fire in at least `MIN_PATTERN_ROUNDS` (4) rounds across at least
  `MIN_PATTERN_MATCHES` (2) matches.
- **Impact score:** `rounds_cost = fired * (win_rate_other_rounds - win_rate_fired_rounds)`.
  This is an observed difference for this player, not a causal claim. Must be > 0.
- **Fix text / drill:** fixed human-written templates filled with counted facts.
- **Metric:** isolated opening deaths at that place per 100 rounds on that side.
  Target: half the baseline, over the next 3 matches on that map.

## 2b. Detector: untraded_death

- **Trigger (per round):** the player dies to an enemy, at least one teammate is still alive,
  and the killer is not killed by the player's team within `TRADE_WINDOW` (5 s).
  Excluded: last-alive deaths, suicides/world damage, team kills.
- **Grouping / minimum sample / metric:** same as section 2.
- **Impact score:** same formula, but the comparison is only the other rounds the player
  died in (surviving rounds would flatter the comparison).
- **Known weakness:** on the first 4 real demos 34 of 46 deaths were untraded, so the trigger
  alone is a weak discriminator; the location grouping does most of the work.

## 3. Ranking and output

Per map-side cell, exactly one card:

- `status: "fix"` — the candidate with the highest `rounds_cost` across all detectors (ties: more rounds, then detector, then place name).
  `rounds_cost` uses a different comparison per detector, so cross-detector ranking is approximate.
- `status: "insufficient_data"` — fewer than `MIN_SIDE_ROUNDS` rounds. States how many more are needed.
- `status: "no_fix_found"` — enough rounds, but no pattern passed the minimum sample.

Evidence: up to 3 most recent fired rounds as `{match_id, round, t, place}`.

## 4. Re-check

Given a fix card and newer matches: `fixed` (rate <= target), `improving` (rate < baseline),
`no_change`, or `insufficient_data` (fewer than `MIN_RECHECK_ROUNDS` = 20 side rounds).

## 5. Not built yet

- Demo parser adapter exists (`parse_demo.py`, demoparser2) and ran on 4 real Premier demos, but has no automated tests yet.
- LLM write-up step. Cards currently use the templates directly.
- A statistical-confidence gate (current minimums let through patterns that could be chance).
- More detectors. Benchmarks from a demo corpus.
- Any UI.
