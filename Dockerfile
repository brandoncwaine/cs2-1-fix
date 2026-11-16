# Cloud image: the private website plus the daily demo sync it runs (one always-on Railway
# service). Node for Steam, Python for parsing and the web server.
FROM node:22-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv bzip2 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir demoparser2==0.42.2

WORKDIR /app
COPY ingest/package.json ingest/package-lock.json ingest/
RUN cd ingest && npm ci --omit=dev
COPY ingest/ ingest/
COPY src/ src/
COPY scripts/ scripts/

# Everything that must survive between runs lives on the Railway volume mounted at /data.
ENV ONEFIX_PYTHON=/opt/venv/bin/python \
    ONEFIX_CONFIG_DIR=/data/config \
    ONEFIX_DEMO_DIR=/data/demos \
    ONEFIX_PARSED_DIR=/data/parsed \
    ONEFIX_WEB_DIR=/data/web \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

# Serves the site on $PORT and runs scripts/sync.sh once a day (see src/onefix/web.py).
CMD ["/opt/venv/bin/python", "-m", "onefix.web"]
