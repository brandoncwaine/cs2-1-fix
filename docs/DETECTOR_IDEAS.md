# Detector backlog (16 Nov 2026)

Candidate habits a player could improve, limited to what can be detected **deterministically
from the demo** (hard rules: no LLM, no screen reading, same input → same output). Every
candidate is computed per map-side cell like the built detectors, so the location makes it
map-specific ("you re-peek Window on Mirage CT").

Status: ideas only. Nothing here is validated. Each idea becomes a detector only with a SPEC
entry (name / trigger / minimum sample / impact score / fix text / drill / metric), tests, and
a check on target-skill demos (see HANDOFF, "Known problems" 1).

Out of scope by design: communication (no voice data), "game sense" that only shows in comms,
and anything needing a per-map lineup library (no source for one yet).

## Data the parser has today

Kills only (`models.Kill`): time, attacker, victim, sides, victim place and position, living
teammates' positions (not labelled by player), and since schema 2 the analysed player's own
position and place at each kill. Everything else below needs `parse_demo.py` and the schema extended. All
of it is available from demoparser2 events or tick fields.

## Candidates

### Positioning and deaths
| # | Habit | Trigger sketch | Data needed |
|---|---|---|---|
| 1 | Dying alone at first contact | *Built:* `isolated_opening_death` | have it |
| 2 | Dying where nobody can trade you | *Built:* `untraded_death` (excludes outnumbered deaths) | have it |
| 3 | **Not trading a teammate** | *Built:* `missed_trade` (SPEC 2d) | have it (schema 2) |
| 4 | **Re-peeking after a kill** | *Built:* `repeek_death` (SPEC 2e) | have it (schema 2) |
| 5 | Dying to the same angle repeatedly | Killer positions cluster at one spot across rounds | killer position |
| 6 | Dying while reloading | A reload started < ~2 s before your death | `weapon_reload` |
| 7 | Dying while flashed | You are blind at the moment of death | `player_blind` |

### Utility
| # | Habit | Trigger sketch | Data needed |
|---|---|---|---|
| 8 | **Dying with unused utility** | Grenades in your inventory at death | inventory at death tick |
| 9 | **Flashing your own team** | Your flashes blind teammates longer than enemies | `player_blind` (attacker, duration) |
| 10 | Flashes that blind nobody | Your flash detonates, no enemy blinded | `player_blind`, `flashbang_detonate` |
| 11 | Entering a site without a flash | Your first contact on a site with no team flash in the previous ~3 s | grenade events, site places |
| 12 | Utility doing no damage | HE / molotov damage per round near zero | `player_hurt` by weapon |

### Economy and decisions
| # | Habit | Trigger sketch | Data needed |
|---|---|---|---|
| 13 | **Not saving** | You die with high equipment value in a round already lost | equipment value, alive counts |
| 14 | Buying out of sync with the team | Your spend far from teammates' in the same round | money / equipment value at freeze end |
| 15 | Late rotations (CT) | You reach the site long after the plant or first contact | positions over time, bomb events |
| 16 | Exposed post-plant | After planting, you die at the same spot before the bomb timer runs out | `bomb_planted`, kills |

### Mechanics
| # | Habit | Trigger sketch | Data needed |
|---|---|---|---|
| 17 | **Shooting while moving** | Rifle shots while speed is above a set limit (no counter-strafe) | `weapon_fire`, velocity |
| 18 | Spraying at long range | Hits per shot fall off sharply beyond a set distance | `weapon_fire`, `player_hurt`, positions |
| 19 | Crosshair too low | View angle vs enemy head height when the enemy becomes visible | view angles + visibility (hard) |

## Suggested first picks (lower-skill players)

Common at lower ranks, unambiguous to detect, easy to explain:

1. **#8 Dying with unused utility**: easy to detect and very common.
2. **#3 Not trading a teammate**: built 16 Nov 2026.
3. **#9 Flashing your own team**: obvious once the evidence rounds are shown.
4. **#4 Re-peeking after a kill**: built 16 Nov 2026.
5. **#17 Shooting while moving**: the most common mechanical fault.

#3 and #4 were built first. The earlier note that they needed no parser changes was wrong:
teammate positions in a kill are not labelled, so the parser now also writes the analysed
player's own position (schema 2). Results on real data are in HANDOFF; both are weak on pro
demos, and every added detector tightens the confidence gate for all the others (Bonferroni),
so add detectors that fire rarely and cost a lot, not many loose ones.

Next: #8 (inventory at death) and #9 (`player_blind`), both of which need new parser fields.

## Open design questions

- **Impact score for mechanics.** The current score compares round win rates, which suits
  round-level habits (#1-5, #8, #13). Mechanical habits (#17, #18) fit a duel-based score
  better: how often you win the fight when you do it vs when you don't. Decide before building
  them; cross-detector ranking (`rounds_cost`) is already only approximate.
- **Thresholds** (trade range, "same place", speed limit, "high equipment value") are guesses
  until checked on target-skill demos. Do not tune them to make cards appear.
- **Map knowledge** (lineups, standard positions) would unlock more ideas, but needs a source.
