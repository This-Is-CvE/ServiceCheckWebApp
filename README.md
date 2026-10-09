# Service Check & Onboarding

Web-App für MSP-Vertragsanbahnung und Kunden-Onboarding.

* **Modul 1 – Service Check:** Pro Managed Service gibt es ein oder mehrere Produkte, jedes mit einem
  anpassbaren Katalog technischer Parameter (Gewichtung 1–10, optional K.O.-Kriterium, Empfehlung bei Abweichung).
  Der Check ergibt eine Ampel (Grün/Gelb/Rot), einen Score und einen PDF-Report mit Empfehlungen für das Vorprojekt.
* **Modul 2 – Onboarding:** Je Produkt (und optional je Erweiterung) eine Vorlage mit allgemeinen Informationen,
  mehreren Ansprechpartnern, installierter technischer Basis (inkl. Modell und Seriennummer) sowie Checklisten (Onboarding-Aufgaben und Voraussetzungen für die Serviceerbringung).
  Das Onboarding lässt sich erst abschließen, wenn alle Pflichtpunkte erledigt sind.

Stack: FastAPI · SQLAlchemy · PostgreSQL (lokal SQLite) · React/Vite · ReportLab (PDF).

## Bewertungslogik

`Score = Σ(Gewicht × Faktor) / Σ(Gewicht)` über alle anwendbaren Parameter
(Erfüllt = 1, Teilweise = 0,5, Nicht erfüllt = 0, „n. a." wird ignoriert).

| Ampel | Bedingung |
|-------|-----------|
| Rot   | ein K.O.-Parameter ist „Nicht erfüllt" **oder** Score < Gelb-Schwelle |
| Gelb  | Score < Grün-Schwelle **oder** ein K.O.-Parameter ist nur „Teilweise" |
| Grün  | sonst |

Schwellwerte (Standard 80 % / 50 %) sind pro Produkt einstellbar. Beim Start eines Checks wird der Katalog als
Kopie übernommen – spätere Katalogänderungen verändern bestehende Checks nicht. Ebenso bei Onboarding-Vorlagen.

## Start mit Docker (PostgreSQL)

```bash
export SECRET_KEY=$(openssl rand -hex 32)
export ADMIN_PASSWORD='bitte-ändern'
docker compose up --build
```

Danach auf http://localhost:8000 mit `admin` und dem gesetzten Passwort anmelden.

## Entwicklung

```bash
# Backend (SQLite-Datei servicecheck.db)
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload      # Standard-Login: admin / admin

# Frontend (separates Terminal, Proxy auf :8000)
cd frontend && npm install && npm run dev        # http://localhost:5173

# Tests
cd backend && pytest
```

## Konfiguration (Umgebungsvariablen)

| Variable | Bedeutung | Standard |
|----------|-----------|----------|
| `DATABASE_URL` | SQLAlchemy-URL | `sqlite:///./servicecheck.db` |
| `SECRET_KEY` | JWT-Signatur – **in Produktion setzen** | Dev-Wert |
| `ADMIN_USER` / `ADMIN_PASSWORD` | initialer Administrator (nur beim ersten Start) | `admin` / `admin` |
| `REPORT_COMPANY` | Firmenname in den PDF-Fußzeilen | „PCO" |
| `STORAGE_BACKEND` | Ablage der Dokument-PDFs: `db` oder `azure` (Blob Storage) | `db` |
| `AZURE_STORAGE_ACCOUNT_URL` / `AZURE_STORAGE_CONTAINER` | Blob-Konto (Anmeldung per Managed Identity) und Container | – / `documents` |
| `AZURE_STORAGE_CONNECTION_STRING` | nur Entwicklung (z. B. Azurite) | – |
| `AUTH_LOCAL_ENABLED` | lokale Benutzer/Passwörter erlauben (`0` = nur Entra ID) | `1` |
| `OIDC_TENANT_ID`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI` | Anmeldung mit Microsoft Entra ID, siehe `docs/azure-deployment.md` | – |
| `OIDC_ADMIN_ROLE` / `OIDC_USER_ROLE` | Namen der Entra-App-Rollen | `ServiceCheck.Admin` / `ServiceCheck.Consultant` |
| `SEED_DEMO_DATA` | `1` legt beim ersten Start einen Beispielkatalog an (vSphere/Hyper-V); sonst startet die App mit leerem Katalog | `0` |

## Kataloge selbst anlegen

Die App startet standardmäßig **ohne** Katalog. Als Administrator unter „Kataloge & Vorlagen": Managed Service anlegen → Produkt
anlegen → Parameter im Basiskatalog hinzufügen (Kategorie, Prüffrage, Gewichtung, K.O., Empfehlung; „Speichern & nächster"
für schnelles Erfassen) → bei Bedarf „+ Erweiterung“ mit eigenem Katalog. Jedes neue Produkt erhält eine
Standard-Onboarding-Vorlage (Reiter „Onboarding-Punkte“), die ebenfalls editierbar ist; auch Erweiterungen können
zusätzliche Onboarding-Punkte mitbringen.

## Onboarding-Dokument

Jedes Onboarding lässt sich als PDF (mit Logo, allgemeinen Angaben, technischer Basis, Checklisten und
Unterschriftenfeldern) herunterladen und für den Kunden verwenden. „PDF ablegen" speichert den aktuellen Stand als
unveränderliches Dokument in der Datenbank beim Onboarding; beim Abschluss wird automatisch eines abgelegt.
Das Logo liegt unter `backend/app/assets/logo.png` (PDF) und `frontend/public/logo.png` (Oberfläche).

## Betrieb, Sicherung, Azure

* Das Datenbankschema wird per **Alembic-Migration** beim Start angelegt bzw. aktualisiert. Eine Datenbank, die noch mit
  der ersten Version (ohne Migrationen) angelegt wurde, muss neu erstellt werden: `docker compose down -v`.
* Mit PostgreSQL startet die App nur, wenn `SECRET_KEY` und `ADMIN_PASSWORD` gesetzt sind.
* Sicherung/Wiederherstellung per `scripts/backup.sh` und `scripts/restore.sh` (pg_dump).
* Betrieb in Azure (App Service, PostgreSQL Flexible Server, Blob Storage, Entra ID): **`docs/azure-deployment.md`**.

Tests gegen PostgreSQL: `TEST_DATABASE_URL=postgresql+psycopg://user@host/db pytest` (Datenbank wird nicht geleert, am besten eine leere Test-Datenbank nehmen).

## Beispieldaten (optional, `SEED_DEMO_DATA=1`)

Managed Service *Managed Virtual Infrastructure* mit den Produkten *VMware vSphere* (Erweiterung *vSAN*) und
*Microsoft Hyper-V* (Erweiterungen *S2D* und *Azure Local*) mit je rund 17–20 Basisparametern sowie Onboarding-Vorlagen. Gewichtungen, K.O.-Kriterien und Texte sind
Vorschläge und sollten fachlich geprüft werden; alles ist in der App unter „Kataloge & Vorlagen" änderbar.

## Bekannte Grenzen

* Kein Kundenportal; Anmeldung nur für interne Nutzer (lokal oder Entra ID).
* Kein Änderungsprotokoll und keine Sperre nach Fehlversuchen bei der lokalen Anmeldung.
* Die PDF-Layouts sind in ReportLab umgesetzt (`backend/app/pdf_report.py`, `pdf_onboarding.py`) und lassen sich dort anpassen.
