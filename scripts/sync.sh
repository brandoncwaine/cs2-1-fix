#!/bin/sh
# Fetch new demos from Steam, parse any not yet parsed, print the cards.
# Usage (from the repo root): scripts/sync.sh
set -eu
cd "$(dirname "$0")/.."

CONFIG="${ONEFIX_CONFIG_DIR:-$HOME/.config/onefix}/steam.json"
PY=.venv/bin/python

(cd ingest && node sync.mjs)

STEAMID=$($PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["steamid"])' "$CONFIG")
DEMOS=$($PY -c 'import json,os,sys; print(os.path.expanduser(json.load(open(sys.argv[1]))["demoDir"]))' "$CONFIG")
OUT=parsed/own
mkdir -p "$OUT"

for dem in "$DEMOS"/*.dem; do
  [ -e "$dem" ] || continue
  name=$(basename "$dem" .dem)
  [ -e "$OUT/$name.json" ] && continue
  PYTHONPATH=src $PY -m onefix.parse_demo --steamid "$STEAMID" --out "$OUT" "$dem"
done

set -- "$OUT"/*.json
if [ -e "$1" ]; then
  PYTHONPATH=src $PY -m onefix.cli --steamid "$STEAMID" "$@"
else
  echo "No parsed matches yet."
fi
