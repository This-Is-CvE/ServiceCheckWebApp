#!/usr/bin/env bash
# Spielt eine Sicherung in eine LEERE Datenbank zurück (bestehende Objekte werden vorher entfernt).
# Nutzung:  PGURL='postgresql://user:pw@host:5432/db' ./scripts/restore.sh servicecheck_....dump
# Die App vorher stoppen. Nach dem Rückspielen startet sie normal; fehlende Migrationen werden beim Start nachgezogen.
set -euo pipefail
: "${PGURL:?PGURL (libpq-Verbindungs-URL) muss gesetzt sein}"
FILE="${1:?Pfad zur .dump-Datei angeben}"
read -r -p "Datenbank '${PGURL%%\?*}' mit '$FILE' überschreiben? (ja/nein) " ANSWER
[[ "$ANSWER" == "ja" ]] || { echo "Abgebrochen."; exit 1; }
pg_restore --clean --if-exists --no-owner --dbname="$PGURL" "$FILE"
echo "Wiederherstellung abgeschlossen."
