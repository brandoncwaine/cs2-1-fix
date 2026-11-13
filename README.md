# cs2-one-fix

Post-match analysis for CS2: one prioritised fix per map and side, with evidence rounds,
a drill and a metric to re-check. Unofficial; not affiliated with Valve.

See `SPEC.md` for formats and detectors, `CLAUDE.md` for project rules.

```
pip install demoparser2
PYTHONPATH=src python -m onefix.parse_demo --steamid <steamid64> --out parsed demos/*.dem
PYTHONPATH=src python -m onefix.cli --steamid <steamid64> parsed/*.json
python -m pytest
```
