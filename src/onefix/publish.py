"""Parse each player's new demos, build their cards and write the website's data file.

Usage: python -m onefix.publish --manifest manifest.json --parsed DIR --out DIR --now ISO_TIME

The manifest comes from `ingest/manifest.mjs`: each player's name, steamid64, demo files and
fetch problems. Parsed matches are kept per player in DIR/<steamid64>/, because one match file
is written from one player's point of view. The output, <out>/data.json, holds no secrets and no
Steam IDs other than the listed players' own. The time is passed in so this module needs no clock.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from onefix.cards import build_cards
from onefix.models import load_match

DATA_FILE = "data.json"


def run_parser(demo: Path, steamid: str, out_dir: Path) -> bool:
    """Parse one demo in a separate process: a broken demo must not stop the others."""
    done = subprocess.run(
        [sys.executable, "-m", "onefix.parse_demo", "--steamid", steamid, "--out", str(out_dir), str(demo)]
    )
    return done.returncode == 0


def publish_player(player: dict, parsed_dir: Path, parse: Callable[[Path, str, Path], bool]) -> dict:
    steamid = player["steamid"]
    out_dir = parsed_dir / steamid
    out_dir.mkdir(parents=True, exist_ok=True)
    parse_failed = 0
    for demo in sorted(Path(d) for d in player.get("demos", [])):
        if (out_dir / f"{demo.stem}.json").exists():
            continue
        if not parse(demo, steamid, out_dir):
            parse_failed += 1
    # Every parsed match counts, including ones whose demo file has since been deleted.
    matches = [load_match(p) for p in sorted(out_dir.glob("*.json"))]
    return {
        "steamid": steamid,
        "name": player["name"],
        "matches": len(matches),
        "rounds": sum(len(m.rounds) for m in matches),
        "cards": build_cards(matches, steamid) if matches else [],
        "problems": {
            "history_error": player.get("history_error"),
            "fetch_failed": player.get("failed", 0),
            "expired": player.get("expired", 0),
            "parse_failed": parse_failed,
        },
    }


def publish(manifest: dict, parsed_dir: Path, now: str,
            parse: Callable[[Path, str, Path], bool] = run_parser) -> dict:
    return {
        "synced_at": now,
        "players": [publish_player(p, parsed_dir, parse) for p in manifest["players"]],
    }


def write_data(data: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / DATA_FILE
    tmp = out_dir / (DATA_FILE + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, dest)  # the web server never sees a half-written file
    return dest


def summary(data: dict) -> str:
    lines = []
    for p in data["players"]:
        by_status: dict[str, int] = {}
        for c in p["cards"]:
            by_status[c["status"]] = by_status.get(c["status"], 0) + 1
        counts = ", ".join(f"{n} {s}" for s, n in sorted(by_status.items())) or "no cards"
        lines.append(f"{p['name']}: {p['matches']} match(es), {p['rounds']} rounds; {counts}")
        for c in p["cards"]:
            if c["status"] == "fix":
                lines.append(f"  FIX {c['map']} {c['side']}: {c['fix_text']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--parsed", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--now", required=True)
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    data = publish(manifest, Path(args.parsed), args.now)
    dest = write_data(data, Path(args.out))
    print(summary(data))
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
