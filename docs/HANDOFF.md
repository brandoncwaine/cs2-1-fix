# Handoff — state as of 13 Nov 2026

Read this with CLAUDE.md, SPEC.md and DECISIONS.md before changing anything.

## What exists
- `models.py`: normalised match schema. `parse_demo.py`: .dem -> that schema via demoparser2.
- Detectors: `isolated_opening_death`, `untraded_death`. `cards.py`: one card per map-side, re-check.
- Confidence gate (SPEC 3a): one-sided Fisher exact test, Bonferroni over patterns tested per cell.
- 53 tests pass. 46 on synthetic data (`tests/builders.py`); 7 parser tests on a public HLTV
  demo kept outside git (`tests/test_parse_demo.py`, skipped if the demo is missing).
- Environment: system Python is 3.9, too old. Use the project venv (Python 3.12, gitignored):
  `.venv/bin/python -m pytest`. `demoparser2` is installed there too.

## What real data showed (4 of Brandon's Mirage Premier demos, 81 rounds, all wins)
- Parser cross-checked on one round against Rankacy's report (death time matched).
- `isolated_opening_death`: fired 2 times in 81 rounds. Too rare to ever produce a card. 13 opening deaths total; team won 8 of those rounds.
- `untraded_death`: 34 of 46 deaths were untraded, so the trigger is a weak discriminator. Cards produced:
  - T / PalaceInterior: 4 rounds in 3 matches, 0 of 4 won vs 8 of 24 other death rounds.
  - CT / BombsiteA: 5 rounds in 3 matches, 2 of 5 won vs 8 of 13.
- Neither card is statistically solid (0 of 4 at a 33% base rate happens by chance ~1 in 5).
- With the confidence gate (re-run 13 Nov 2026), both cells are now `no_fix_found`:
  - T: 2 patterns tested (also BombsiteA, 1/6 vs 7/22); Palace p = 0.237, needed <= 0.025.
  - CT: 1 pattern tested; BombsiteA p = 0.382, needed <= 0.05.
- If the Palace pattern holds at the same rate (~1 lost death per match), it would pass the gate
  after roughly 11-12 Mirage matches. That is a projection, not a finding.
- Pending: Brandon to watch the four Palace rounds and say whether the habit is real.

## What pro demos showed (Bluejays, 4 Mirage maps from Hugging Face, 76 rounds per player)
- Parser works on HLTV GOTV demos. Each has a junk `round_end` at tick 6 (no winner) before
  round 1; the parser already skips it. Round timer confirms TICKRATE = 64.
- All 5 players: `no_fix_found` on both sides (best p = 0.365). 4 matches is too few, as expected.
- `untraded_death` fires on 50-72% of deaths for pros too: confirms it is a weak discriminator.
- `isolated_opening_death`: 0-3 events per player in 76 rounds. Rare in pro play as well.

## What 14 MOUZ Mirage maps showed (HLTV, 2026 events, 335 rounds per player, 16 Nov 2026)
- Same 5 players in all 14 maps. Parser correct on all: every map gives a valid score (incl.
  16-14 and 19-16 overtimes). One demo has no junk `round_end`; handled.
- Still no card for any player. 3-9 patterns tested per cell, so thresholds are 0.0056-0.0167.
  Closest: xertioN CT untraded at BombsiteB, 0/6 vs 50/90, p = 0.0101 vs 0.01 needed.
- Main finding: of 679 untraded deaths (all 5 players), 244 happened when the player's team was
  already outnumbered; those rounds were won 3% of the time, vs 45% for the rest. These deaths
  mostly reflect a lost round, not a habit, and they add noise. Several near-misses are
  dominated by them (late bombsite deaths at 2v3, 3v5).
- Exception: xertioN T untraded at TopofMid (0/9, p = 0.040) is mostly 5v5 deaths at 8-15 s:
  the shape of a real early-round habit.
- `isolated_opening_death`: 1-16 events per player in 335 rounds.
- Product implication: even 14 maps on one map gives no card with the current detectors.
  Sharper triggers (bigger effect per event) are the fix, not a looser gate.

## Known problems, in priority order
1. Data mismatch: detectors are only checked on pro demos and Brandon's 4 matches. The buyers
   are lower-skill players; their patterns, base rates and thresholds are unmeasured.
2. D3 needs ~15 maps of one map per player for a card. Brandon reaffirmed per-map (16 Nov), so
   the answer is automatic ingestion (D7) to get volume, plus sharper detectors.
3. All thresholds are unvalidated guesses (900 units, 5 s trade window, target = half baseline,
   ALPHA = 0.05). The gate treats rounds as independent, which they are not.
4. `rounds_cost` uses a different comparison set per detector, so cross-detector ranking is approximate.
5. Parser: tick rate hard-coded to 64 (checked on one demo, not read from the file); match date
   is empty (sorted by match id in file name); split demos (`-p1`/`-p2`) would load as two matches.

Built 16 Nov 2026: `untraded_death` excludes deaths when the team is already outnumbered, and
compares like for like (SPEC 2b, 2c). Effect: Brandon 34 -> 25 events, T/PalaceInterior pattern
gone (those deaths were mostly a player down); MOUZ events down 31-50%. Still no cards anywhere.

Fixed: both detectors now share the enemy-kill and trade rules (`detectors/common.py`, SPEC 2c).
A trade must be made by the victim's team. No change in counts on the 4 real demos.

## Suggested next steps
- Ingestion works end to end (16 Nov 2026): share code -> bot -> GC -> 199 MB demo, named like
  client downloads, parsed, cards printed. Run `scripts/sync.sh` at least weekly (Valve deletes
  demos after a few weeks). Railway daily cron prepared (Dockerfile, railway.json); deploy
  to Brandon's personal Railway account pending his login.
- Stop using pro demos to judge detectors (keep them for parser tests). Get target-skill data:
  Brandon's ongoing matches plus 3-5 friends at his level, 15-20 matches each, and ask each
  player whether their card is right. That is both validation data and customer research.
- The outnumbered exclusion came from pro data: confirm it on target-skill demos.
- Do not tune thresholds or ALPHA to make cards appear on this small sample.

## Local data
- Demos are not in git. Paths and Brandon's steamid64 are in `docs/LOCAL.md` (gitignored;
  the repo is public).
- Never commit `.dem` files or parsed output (other players' Steam IDs).

## Demo sources (checked 13 Nov 2026)
- Own matches: CS2 client, Watch > Your Matches (recent only; download regularly).
- HLTV match pages: demo download per series. Blocks scripted access (403), so download by hand.
  Best way to get depth: many maps on one map for one team, then analyse one player.
- Hugging Face `aldigobbler/cs2demos`: 177 HLTV demos (tier 2-3), ~80 GB, ~400 MB each, no
  licence stated. Max 4 maps of one team on one map, so useful for parser robustness and
  population base rates, not for single-player depth. Some maps split into `-p1`/`-p2` files.
- Pro demos as a product benchmark corpus: licensing still unresearched (DECISIONS, Open).
