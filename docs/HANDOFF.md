# Handoff — state as of 13 Nov 2026

Read this with CLAUDE.md, SPEC.md and DECISIONS.md before changing anything.

## What exists
- `models.py`: normalised match schema. `parse_demo.py`: .dem -> that schema via demoparser2.
- Detectors: `isolated_opening_death`, `untraded_death`. `cards.py`: one card per map-side, re-check.
- Confidence gate (SPEC 3a): one-sided Fisher exact test, Bonferroni over patterns tested per cell.
- 41 tests pass, all on synthetic data (`tests/builders.py`). `parse_demo.py` has no tests.
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

## Known problems, in priority order
1. All thresholds are unvalidated guesses (900 units, 5 s trade window, target = half baseline,
   ALPHA = 0.05). The gate treats rounds as independent, which they are not.
2. `rounds_cost` uses a different comparison set per detector, so cross-detector ranking is approximate.
3. `untraded_death` needs better exclusions (e.g. deaths after the round is effectively lost).
4. Parser: no tests; tick rate hard-coded to 64; match date is empty (sorted by match id in file name).

Fixed: both detectors now share the enemy-kill and trade rules (`detectors/common.py`, SPEC 2c).
A trade must be made by the victim's team. No change in counts on the 4 real demos.

## Suggested next steps
- Add parser tests using a small real demo kept outside git.
- Get more demos: 4 matches cannot produce a card that passes the gate.
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
