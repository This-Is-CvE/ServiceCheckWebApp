#!/usr/bin/env bash
# Logische Sicherung der Datenbank (pg_dump, Custom-Format) mit Aufbewahrung.
# Nutzung:  PGURL='postgresql://user:pw@host:5432/db?sslmode=require' ./scripts/backup.sh [Zielverzeichnis] [Tage]
# Optional: BACKUP_BLOB_URL='https://<konto>.blob.core.windows.net/<container>' -> zusätzlich per azcopy hochladen
#           (azcopy muss angemeldet sein, z. B. 'azcopy login --identity').
set -euo pipefail
: "${PGURL:?PGURL (libpq-Verbindungs-URL) muss gesetzt sein}"
DIR="${1:-./backups}"
KEEP_DAYS="${2:-14}"
mkdir -p "$DIR"
FILE="$DIR/servicecheck_$(date +%Y-%m-%d_%H%M%S).dump"
pg_dump --format=custom --no-owner --dbname="$PGURL" --file="$FILE"
pg_restore --list "$FILE" > /dev/null   # Datei ist lesbar und vollständig
echo "Sicherung erstellt: $FILE ($(du -h "$FILE" | cut -f1))"
if [[ -n "${BACKUP_BLOB_URL:-}" ]]; then
  azcopy copy "$FILE" "${BACKUP_BLOB_URL%/}/$(basename "$FILE")" --overwrite=false
fi
find "$DIR" -name 'servicecheck_*.dump' -mtime +"$KEEP_DAYS" -delete
