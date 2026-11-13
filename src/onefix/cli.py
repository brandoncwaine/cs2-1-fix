"""Usage: python -m onefix.cli --steamid <id> match1.json match2.json ..."""
from __future__ import annotations

import argparse
import json

from onefix.cards import build_cards
from onefix.models import load_match


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steamid", required=True)
    ap.add_argument("matches", nargs="+")
    args = ap.parse_args()
    matches = [load_match(p) for p in args.matches]
    print(json.dumps(build_cards(matches, args.steamid), indent=2))


if __name__ == "__main__":
    main()
