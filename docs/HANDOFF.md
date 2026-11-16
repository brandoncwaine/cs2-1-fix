# Handoff — state as of 13 Nov 2026

Read this with CLAUDE.md, SPEC.md and DECISIONS.md before changing anything.

## What exists
- `models.py`: normalised match schema. `parse_demo.py`: .dem -> that schema via demoparser2.
- Detectors: `isolated_opening_death`, `untraded_death`, `missed_trade`, `repeek_death`. `cards.py`: one card per map-side, re-check.
- Confidence gate (SPEC 3a): one-sided Fisher exact test, Bonferroni over patterns tested per cell.
- 86 tests pass. 78 on synthetic data (`tests/builders.py`); 8 parser tests on a public HLTV
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

## Two new detectors on real data (16 Nov 2026, match files re-parsed as schema 2)
- `missed_trade` (SPEC 2d) and `repeek_death` (SPEC 2e) needed the player's own position at each
  kill, so the match format is now schema 2. Old parsed matches are parsed again on the next
  sync while their demo is on disk (on Railway: all of them, demos are never deleted).
- Still no card for anyone: Brandon (4 Mirage maps, 81 rounds) or the 5 MOUZ players (14 maps).
- `missed_trade`: fires in 55-67% of the rounds with a chance to trade, pros included, so
  "within 900 units" is too generous to mean "should have traded". Summed over all places it
  does track losing for some players (torzsi 38/91 won vs 33/47; pr 21/57 vs 22/31), but split
  by place the samples are small. Brandon: 18 fired (10 won) vs 16 other (11 won).
- `repeek_death`: 11-41 events per pro in 335 rounds; Brandon 3 in 81. No sign it costs rounds
  (xertioN won 20 of 24). Not moving after a kill is not obviously a mistake at pro level;
  unknown at lower ranks.
- Cost of adding detectors: more patterns reach the minimum sample, so the Bonferroni threshold
  tightens. MOUZ cells now have 4-12 patterns tested (thresholds 0.004-0.0125), up from 3-9 in
  the first run. Two weak detectors make a card less likely, not more.
  Open decision: keep both in `cards.DETECTORS`, or hold weak ones back until target-skill data
  shows they separate won and lost rounds.

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

## Frontend (built 16 Nov 2026, DECISIONS D8 and D9)
- `onefix.web`: invite-only site (D9). Sign in through Steam, enter the invite code and your own
  two Steam codes, then one card per map and side (fix / no fix found / not enough rounds). Each
  person sees only their own cards; the owner (`ONEFIX_STEAMID`) sees everyone's and can remove
  people. Users live in `/data/config/onefix.db`; `scripts/sync.sh` exports them to the ingest step
  and deletes removed users' parsed matches and fetch history before each sync.
- The owner is an ordinary member in the database too (copied in once from the environment
  variables at start-up; flag `owner_imported` in `onefix.db`). After that `STEAM_MATCH_AUTH_CODE`,
  `ONEFIX_FIRST_SHARE_CODE` and `ONEFIX_PLAYER_NAME` are ignored; `ONEFIX_STEAMID` still says who
  the owner is. The owner needs no invite code and does not count against a full site.
- `/login` is a short landing page for invited people (16 Nov 2026): headline, one action repeated
  ("Sign in through Steam"), a "Video coming soon" placeholder under the hero (Brandon will record
  a how-it-works video), four one-line steps, two sample fix cards and short questions. Brandon
  wants little text on this page and wants the examples to be fix cards, not the empty states.
  Still `noindex`. The sample cards are shortened by hand from the `fixtures/` output (Mirage T
  and Inferno CT; `scripts/make_fixtures.py`): update them if the fixtures or card numbers change.
- Every card, on both pages, has a map screenshot banner (D10; pictures in `static/maps/`, one per
  map, served through `STATIC_FILES` in `web.py`, chosen by the class `map-<name>` in `app.css`;
  a map with no picture gets a plain banner). Card titles are plain words ("Dying first and
  alone", "Dying untraded": `DETECTOR_TITLES` in `app.js`).
- Fix cards are short on purpose (Brandon, 16 Nov 2026: no walls of text, percentages not round
  counts). Front: title, "Happens in N% of your T rounds", two win-rate bars (when it happens /
  the comparison rounds), and a "How to fix it" button. The button opens a modal with the advice
  (`advice` in the card JSON; falls back to `fix_text` for data written before it existed), the
  drill, the target as percentages, the rounds to watch and the raw numbers. On `/login` the
  sample cards show the drill in a box instead (no script on that page).
- The site's content security policy blocks `style="..."` attributes in the HTML, so static pages
  must use classes. Check pages through the local server, not a file harness, or this is missed.
  Preview with sample data: copy `fixtures/*.json` into `<parsed>/<steamid>/`, replace `"me"` with
  that steamid, run `onefix.publish`, and start `onefix.web` with `ONEFIX_WEB_DIR` and
  `ONEFIX_CONFIG_DIR` pointing at scratch folders.
- Checked: unit tests for the sign-in check, accounts and who-sees-what; screens by eye on sample
  data; Brandon signed in through Steam on the live site as the owner (16 Nov 2026). Not
  checked: a real friend joining (invite code, Steam code check, first sync for a second account).
- Live since 16 Nov 2026 on Brandon's personal Railway: https://cs2-1-fix-production.up.railway.app
  (sign-in page, health check and first sync confirmed; signed-in page not checked from here).

## Railway setup (as of 16 Nov 2026)
- One always-on service `cs2-1-fix` (not a cron), built from GitHub `main` with the Dockerfile;
  every push to `main` redeploys. Runs `python -m onefix.web`: the site, plus the sync at start-up
  when the data is over a day old and daily at 06:00 UTC. IDs are in docs/LOCAL.md.
- The service was deleted and recreated on 16 Nov 2026 (the old one could not be turned from a
  cron into a web service from the CLI). The volume `cs2-1-fix-volume` at `/data` was kept and
  re-attached; its demos and sync state survived.
- Domain routes to port 8080 and the variable `PORT=8080` makes the server listen there. Both
  must agree, or the site returns 502.
- Variables: `PORT`, `ONEFIX_STEAMID`, `ONEFIX_FIRST_SHARE_CODE`, `ONEFIX_WEB_PASSWORD`,
  `STEAM_WEB_API_KEY`, `STEAM_MATCH_AUTH_CODE`, `BOT_REFRESH_TOKEN`. `ONEFIX_WEB_PASSWORD` is now
  the invite code (rename to `ONEFIX_INVITE_CODE` when convenient). Not set yet:
  `ONEFIX_PLAYER_NAME` (the site shows "Me"). Table in
  ingest/README.md. Without an invite code nobody new can join; without the two Steam secrets the site runs but every sync fails.
- `railway.json` supplies the builder, health check (`/healthz`) and restart policy. A cron
  schedule set on the service is not removed by leaving it out of the file: clear it in the
  dashboard (Settings > Deploy). `railway environment edit --service-config` (CLI 5.41.3)
  reported "No changes to apply" for every setting tried; `railway add`, `railway variable set`,
  `railway volume attach` and `railway domain` worked.
- Untested: the bot login from the cloud since the service was recreated. The first sync had no
  new matches, so the bot was not needed. If the logs say "bot login failed", run
  `npm run login -- --fresh` in `ingest/` and replace `BOT_REFRESH_TOKEN`.
- Logs: `railway logs --service cs2-1-fix` (the CLI is logged in to the personal account; the
  Railway MCP is on the work account and cannot see this project).
- Not built: re-check on the site (`cards.recheck` exists but nothing stores the card a player
  was given, so there is nothing to re-check against yet); match dates (parser writes none);
  a privacy policy and anything else needed before opening to the public.
- Volume use grows ~200 MB per match and old demos are never deleted. Parsed matches are kept,
  so demos could be deleted after parsing, but then a parser fix cannot be re-run on them.

## Suggested next steps
- Ingestion works end to end (16 Nov 2026): share code -> bot -> GC -> 199 MB demo, named like
  client downloads, parsed, cards printed. Run `scripts/sync.sh` at least weekly (Valve deletes
  demos after a few weeks). On Railway it now runs daily inside the web service (see Railway setup).
- Stop using pro demos to judge detectors (keep them for parser tests). Get target-skill data:
  Brandon's ongoing matches plus 3-5 friends at his level, 15-20 matches each, and ask each
  player whether their card is right. That is both validation data and customer research.
- The outnumbered exclusion came from pro data: confirm it on target-skill demos.
- Do not tune thresholds or ALPHA to make cards appear on this small sample.
- New detectors: candidates and first picks in `docs/DETECTOR_IDEAS.md` (#3 and #4 need no
  parser changes).

## Notes for building a UI (16 Nov 2026)
- **Input is the card JSON** (`cards` per player in `data.json`; same as `onefix.cli` prints) (built in `src/onefix/cards.py`; formats in SPEC 3).
  One card per (map, side), three statuses:
  - `fix`: `detector`, `place`, `fix_text`, `drill`, `evidence[] {match_id, round, t, place}`,
    `metric {name, baseline, target, window_matches}`, `stats {fired_rounds,
    matches_with_pattern, win_rate_fired_pct, win_rate_other_pct, comparison_rounds,
    rounds_cost, p_value, p_threshold, patterns_tested, note}`.
  - `insufficient_data`: `reason`, `rounds_needed`.
  - `no_fix_found`: `patterns_tested`, `reason`.
  `cards.recheck()` (fixed / improving / no_change / insufficient_data) exists but is not in
  the CLI output yet.
- **Design for "no fix" as the normal state.** Every real player so far (Brandon, 10 pros)
  gets only `insufficient_data` / `no_fix_found`. Show progress honestly (rounds needed per
  map-side). Never invent or soften a card to fill the screen (D3).
- **Example fix card**: `PYTHONPATH=src python -m onefix.cli --steamid me fixtures/*.json`
  (made-up data from `scripts/make_fixtures.py`: one fix, one no-fix and two thin cells).
- **Rules that bind the UI**: every claim links to its evidence rounds (D2); one card per map
  and side (D3, reaffirmed); no Valve / Counter-Strike logos or implied affiliation (D4);
  `stats.note` says the cost is observed, not causal: keep that framing.
- **Where the data lives** (decided, D8): the UI is served from the same service as the sync.
  `scripts/sync.sh` writes `/data/web/data.json` (all players, see `src/onefix/publish.py`);
  `onefix.web` serves it. `/data/cards.json` is no longer written.
- **Privacy**: parsed match JSON contains other players' Steam IDs; show only the analysed
  player's data, and keep the repo free of real parsed output (it is public).
- Brandon's global preference: verify UI work by rendering it (headless Chrome screenshot),
  not by reasoning about CSS.

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
