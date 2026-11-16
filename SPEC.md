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
  living teammate is further than `ISOLATION_DISTANCE` (900 units), AND the death is an enemy
  kill (not a suicide, world damage or team kill), AND the death was not traded (2c).
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
  the player's team is not outnumbered (2c), and the death was not traded (2c).
  Excluded: last-alive deaths, suicides/world damage, team kills, outnumbered deaths.
- **Grouping / minimum sample / metric:** same as section 2.
- **Impact score:** same formula, but the comparison is only the other rounds the player
  died in before their team was outnumbered (like for like: surviving rounds would flatter the
  comparison, and outnumbered rounds are nearly always lost whatever the player did).
- **Why the outnumbered exclusion (16 Nov 2026):** on 14 pro Mirage maps, 244 of 679 untraded
  deaths came when already outnumbered, and those rounds were won 3% of the time (45% otherwise).
  Caveat: found on pro data; confirm on target-skill demos.
- **Known weakness:** most deaths are untraded, so the trigger alone is a weak discriminator;
  the location grouping does most of the work.

## 2c. Shared rules (`detectors/common.py`)

- **Enemy kill:** attacker is not `world`, not the victim, and `attacker_side != victim_side`.
- **Traded:** within `TRADE_WINDOW` (5 s) after the death, the killer is killed by a player on
  the victim's side (`attacker_side == victim_side`, attacker not `world`). The killer dying to
  world damage, their own team or themselves is not a trade. A kill with no `attacker_side` is
  never a trade, so match files must carry `attacker_side` (the parser always writes it).
- **Outnumbered:** just before the death, the victim's team had fewer players alive than the
  enemy. Own count = victim + `victim_teammates_alive` (exact). Enemy count = 5 minus enemy deaths
  earlier in the round (a short-handed enemy is overcounted). Same-instant kills are not earlier.

## 3. Ranking and output

Per map-side cell, exactly one card:

- `status: "fix"` — among patterns that pass the confidence gate (3a), the one with the highest
  `rounds_cost` across all detectors (ties: more rounds, then detector, then place name).
  `rounds_cost` uses a different comparison per detector, so cross-detector ranking is approximate.
- `status: "insufficient_data"` — fewer than `MIN_SIDE_ROUNDS` rounds. States how many more are needed.
- `status: "no_fix_found"` — enough rounds, but no pattern passed the minimum sample, or none
  passed the confidence gate. Carries `patterns_tested` and a `reason` (with the smallest p-value
  and the threshold it needed when the gate was the blocker).

## 3a. Confidence gate

Every pattern (detector, place) that reaches the minimum sample in a cell is *tested*, whether
or not it shows a cost. For each:

- **p-value:** one-sided Fisher exact test on the 2x2 table (fired rounds: wins/losses vs
  comparison rounds: wins/losses). It is the chance the fired rounds would have this few wins or
  fewer if they were a random draw from all of those rounds. Stdlib `math.comb`, deterministic.
- **Threshold:** `ALPHA / patterns_tested` (Bonferroni), `ALPHA = 0.05`. We pick the best of
  several patterns, so the threshold tightens with how many we looked at.
- **Pass:** `rounds_cost > 0` and `p <= threshold`.

Fix cards report `p_value`, `p_threshold` and `patterns_tested` in `stats`.

Known limits: rounds are treated as independent (they are not: economy and momentum carry over
within a match); Bonferroni counts only patterns that reached the minimum sample, not every
place looked at; `ALPHA` is a convention, not validated against coach labels.

Evidence: up to 3 most recent fired rounds as `{match_id, round, t, place}`.

## 4. Re-check

Given a fix card and newer matches: `fixed` (rate <= target), `improving` (rate < baseline),
`no_change`, or `insufficient_data` (fewer than `MIN_RECHECK_ROUNDS` = 20 side rounds).

## 5. Not built yet

- Demo parser adapter (`parse_demo.py`, demoparser2) is tested only against one public HLTV demo kept outside git (`tests/test_parse_demo.py`).
- LLM write-up step. Cards currently use the templates directly.
- More detectors. Benchmarks from a demo corpus.
- Any UI.
