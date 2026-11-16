#!/bin/sh
# Fetch new demos from Steam for every player, parse any not yet parsed, build the cards and
# write the website's data file.
# Usage (from the repo root): scripts/sync.sh
# Locally it uses ~/.config/onefix/steam.json and .venv; in the cloud image the ONEFIX_*
# environment variables (see ingest/README.md and Dockerfile).
set -eu
cd "$(dirname "$0")/.."

PY="${ONEFIX_PYTHON:-.venv/bin/python}"
PARSED="${ONEFIX_PARSED_DIR:-parsed/own}"
WEB="${ONEFIX_WEB_DIR:-parsed/web}"

# A failed fetch (Steam down, one player's auth code revoked) must not stop the cards being
# rebuilt from what we already have; the script still exits 1 at the end.
status=0
(cd ingest && node sync.mjs) || status=1

MANIFEST=$(mktemp)
trap 'rm -f "$MANIFEST"' EXIT
(cd ingest && node manifest.mjs) > "$MANIFEST"

PYTHONPATH=src "$PY" -m onefix.publish \
  --manifest "$MANIFEST" --parsed "$PARSED" --out "$WEB" --now "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

exit $status
