#!/usr/bin/env bash
#
# Dump the running postgres container to a gzipped SQL file in ./backups/.
# Run from the project root.
#
# Usage:
#   bash scripts/backup-db.sh
#   bash scripts/backup-db.sh /custom/path/dump.sql.gz
#
set -euo pipefail

# Load DB_USER / DB_NAME from .env if present, else fall back to defaults.
if [[ -f .env ]]; then
    # shellcheck disable=SC1091
    set -a; source .env; set +a
fi

DB_USER="${DB_USER:-nielit}"
DB_NAME="${DB_NAME:-nielit_community}"

mkdir -p backups
DEST="${1:-backups/$(date -u +%Y-%m-%d_%H%M%S).sql.gz}"

echo "▸ Dumping $DB_NAME as $DB_USER → $DEST"
docker compose exec -T db pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$DEST"

SIZE=$(du -h "$DEST" | cut -f1)
echo "✓ Done. Backup size: $SIZE"
echo
echo "  To restore:"
echo "    gunzip < $DEST | docker compose exec -T db psql -U $DB_USER $DB_NAME"
