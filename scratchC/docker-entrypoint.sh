#!/bin/bash
#
# Container entrypoint.
#  1. Waits for the PostgreSQL service to accept connections.
#  2. Creates any missing tables (idempotent — safe to run every boot).
#  3. Exec's whatever CMD the image was started with (gunicorn by default).
#
set -e

echo "▸ Waiting for database at ${DATABASE_URL%%@*}@***..."

# Use psycopg2 (already installed) to probe, so we don't need the postgres-client package.
python - <<'PY'
import os, sys, time
from urllib.parse import urlparse
import psycopg2

url = urlparse(os.environ["DATABASE_URL"])
for attempt in range(60):  # ~60s total
    try:
        psycopg2.connect(
            host=url.hostname,
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            dbname=url.path.lstrip("/"),
            connect_timeout=2,
        ).close()
        print(f"✓ Database reachable after {attempt + 1} attempt(s).")
        sys.exit(0)
    except Exception as e:
        if attempt == 0:
            print(f"  (waiting on DB: {e.__class__.__name__})")
        time.sleep(1)
print("✗ Database never became reachable.", file=sys.stderr)
sys.exit(1)
PY

echo "▸ Ensuring database schema..."
flask init-db

echo "▸ Starting: $*"
exec "$@"
