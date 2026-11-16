#!/bin/sh
# Fetch new demos from Steam, parse any not yet parsed, print the cards.
# Usage (from the repo root): scripts/sync.sh
# Locally it uses ~/.config/onefix/steam.json and .venv; in the cloud image the ONEFIX_*
# environment variables (see ingest/README.md and Dockerfile).
set -eu
cd "$(dirname "$0")/.."

PY="${ONEFIX_PYTHON:-.venv/bin/python}"
OUT="${ONEFIX_PARSED_DIR:-parsed/own}"

(cd ingest && node sync.mjs)

STEAMID=$(cd ingest && node config-get.mjs steamid)
DEMOS=$(cd ingest && node config-get.mjs demoDir)
mkdir -p "$OUT"

for dem in "$DEMOS"/*.dem; do
  [ -e "$dem" ] || continue
  name=$(basename "$dem" .dem)
  [ -e "$OUT/$name.json" ] && continue
  PYTHONPATH=src "$PY" -m onefix.parse_demo --steamid "$STEAMID" --out "$OUT" "$dem"
done

set -- "$OUT"/*.json
if [ ! -e "$1" ]; then
  echo "No parsed matches yet."
  exit 0
fi
CARDS=$(PYTHONPATH=src "$PY" -m onefix.cli --steamid "$STEAMID" "$@")
echo "$CARDS"
if [ -n "${ONEFIX_CARDS_OUT:-}" ]; then
  printf '%s\n' "$CARDS" > "$ONEFIX_CARDS_OUT"
fi
