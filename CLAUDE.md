# CS2 One-Fix Coach

Post-match tool: ONE prioritised fix per map and side (evidence, drill, metric), then re-check.

## Hard rules
- No in-game overlays or screen reading. Post-match or practice servers only.
- Detectors are deterministic, tested code. Same input, same output. No LLM, no randomness, no clock.
- The LLM (later) only rewrites card text. It never adds tactical claims. Every claim links to rounds.
- One fix per map and side. Below minimum sample: say "insufficient_data", never guess.
- No Valve / Counter-Strike logos or implied affiliation.
- Decisions live in DECISIONS.md (Claude Project). Do not re-argue them silently.

## Stack
- Python 3.11+, stdlib only in `src/onefix` (parser adapter will add demoparser2 or awpy later).
- Tests: `python -m pytest` from repo root.
- CLI: `PYTHONPATH=src python -m onefix.cli --steamid <id> fixtures/*.json`

## Layout
- `src/onefix/models.py`   normalised match schema (parser-independent)
- `src/onefix/detectors/`  one file per detector
- `src/onefix/cards.py`    ranking, thin-data refusal, card JSON, re-check
- `SPEC.md`                detector catalogue and formats

## Glossary
- Side: T or CT. Half: the rounds played on one side.
- Opening death: first death on a team in a round.
- Trade: a teammate kills your killer within a few seconds of your death.
- Trade range: close enough that a teammate could plausibly trade you.
- Place: the map callout name the demo records for a position (e.g. "PalaceInterior").
- Map-side cell: one (map, side) pair, e.g. (de_mirage, T).

## Detector spec format
name / trigger / minimum sample / impact score / fix text / drill / metric. See SPEC.md.
