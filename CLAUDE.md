# CS2 One-Fix Coach

Post-match tool: ONE prioritised fix per map and side (evidence, drill, metric), then re-check.

## Hard rules
- No in-game overlays or screen reading. Post-match or practice servers only.
- Detectors are deterministic, tested code. Same input, same output. No LLM, no randomness, no clock.
- The LLM (later) only rewrites card text. It never adds tactical claims. Every claim links to rounds.
- One fix per map and side. Below minimum sample: say "insufficient_data", never guess.
- No Valve / Counter-Strike logos or implied affiliation.
- Decisions live in DECISIONS.md. Do not re-argue them silently. Current state and known problems: docs/HANDOFF.md.

## Stack
- Python 3.11+, stdlib only in `src/onefix`, except `parse_demo.py`, which needs demoparser2.
- Use the project venv (`.venv`, Python 3.12; system Python is 3.9). `python` below means `.venv/bin/python`.
- Tests: `python -m pytest` from repo root.
- CLI: `PYTHONPATH=src python -m onefix.cli --steamid <id> fixtures/*.json`
- Website, local preview: `ONEFIX_SYNC_HOUR_UTC=off PYTHONPATH=src python -m onefix.web` (http://127.0.0.1:8000)
- Parse demos: `PYTHONPATH=src python -m onefix.parse_demo --steamid <id> --out parsed demos/*.dem`
- Never commit `.dem` files or `parsed/` output: they contain other players' Steam IDs.
- `ingest/` is a separate Node 20+ package (steam-user, globaloffensive): `npm test` there.
  Its secrets live in `~/.config/onefix/`, never in the repo. Full run: `scripts/sync.sh`.
- Never type, store or log anyone's Steam password. The bot's first login is run by the user.
- The site's data file and page carry no secrets, no share codes and no Steam IDs except the listed players' own.

## Layout
- `src/onefix/models.py`   normalised match schema (parser-independent)
- `src/onefix/parse_demo.py` .dem -> normalised match JSON (tests need a real demo; see tests/test_parse_demo.py)
- `src/onefix/detectors/`  one file per detector (`isolated_opening_death`, `untraded_death`, `missed_trade`, `repeek_death`); shared rules in `common.py`
- `src/onefix/cards.py`    ranking, thin-data refusal, card JSON, re-check
- `src/onefix/publish.py`  per player: parse new demos, build cards, write the site's `data.json`
- `src/onefix/web.py`      private site (shared password) + daily sync scheduler; page in `src/onefix/static/`
- `ingest/`                share codes -> bot account -> game coordinator -> demo download (see ingest/README.md)
- `scripts/sync.sh`        fetch new demos for every player, parse, write the site's data (run daily by `web.py`)
- `Dockerfile`, `railway.json` always-on Railway service: site + daily sync (volume at /data; see ingest/README.md)
- `SPEC.md`                detector catalogue and formats
- `docs/DETECTOR_IDEAS.md` backlog of candidate detectors (ideas, not spec)

## Glossary
- Side: T or CT. Half: the rounds played on one side.
- Opening death: first death on a team in a round.
- Trade: a teammate kills your killer within a few seconds of your death.
- Trade range: close enough that a teammate could plausibly trade you.
- Place: the map callout name the demo records for a position (e.g. "PalaceInterior").
- Map-side cell: one (map, side) pair, e.g. (de_mirage, T).

## Detector spec format
name / trigger / minimum sample / impact score / fix text / drill / metric. See SPEC.md.
