# Service Check & Onboarding

Web-App für MSP-Vertragsanbahnung und Kunden-Onboarding.

* **Modul 1 – Service Check:** Pro Managed Service Offer gibt es ein oder mehrere Produkte, jedes mit einem
  anpassbaren Katalog technischer Parameter (Gewichtung 1–10, optional K.-o.-Kriterium, Empfehlung bei Abweichung).
  Der Check ergibt eine Ampel (Grün/Gelb/Rot), einen Score und einen PDF-Report mit Empfehlungen für das Vorprojekt.
* **Modul 2 – Onboarding:** Je Offer eine Vorlage mit allgemeinen Informationen, installierter technischer Basis
  (Systemliste) sowie Checklisten (Onboarding-Aufgaben und Voraussetzungen für die Serviceerbringung).
  Das Onboarding lässt sich erst abschließen, wenn alle Pflichtpunkte erledigt sind.

Stack: FastAPI · SQLAlchemy · PostgreSQL (lokal SQLite) · React/Vite · ReportLab (PDF).

## Bewertungslogik

`Score = Σ(Gewicht × Faktor) / Σ(Gewicht)` über alle anwendbaren Parameter
(Erfüllt = 1, Teilweise = 0,5, Nicht erfüllt = 0, „n. a." wird ignoriert).

| Ampel | Bedingung |
|-------|-----------|
| Rot   | ein K.-o.-Parameter ist „Nicht erfüllt" **oder** Score < Gelb-Schwelle |
| Gelb  | Score < Grün-Schwelle **oder** ein K.-o.-Parameter ist nur „Teilweise" |
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
| `SEED_DEMO_DATA` | `1` legt beim ersten Start einen Beispielkatalog an (vSphere/Hyper-V); sonst startet die App mit leerem Katalog | `0` |

## Kataloge selbst anlegen

Die App startet standardmäßig **ohne** Katalog. Als Administrator unter „Kataloge & Vorlagen": Offer anlegen → Produkt
anlegen → Parameter hinzufügen (Kategorie, Prüffrage, Gewichtung, K.-o., Empfehlung; „Speichern & nächster" für
schnelles Erfassen). Jedes neue Offer erhält eine Standard-Onboarding-Vorlage, die ebenfalls editierbar ist.

## Onboarding-Dokument

Jedes Onboarding lässt sich als PDF (mit Logo, allgemeinen Angaben, technischer Basis, Checklisten und
Unterschriftenfeldern) herunterladen und für den Kunden verwenden. „PDF ablegen" speichert den aktuellen Stand als
unveränderliches Dokument in der Datenbank beim Onboarding; beim Abschluss wird automatisch eines abgelegt.
Das Logo liegt unter `backend/app/assets/logo.png` (PDF) und `frontend/public/logo.png` (Oberfläche).

## Beispieldaten (optional, `SEED_DEMO_DATA=1`)

Offer *Managed Virtual Infrastructure* mit *VMware vSphere (inkl. vSAN)* und *Microsoft Hyper-V (inkl. S2D und
Azure Local)* – je rund 20–25 Parameter – sowie eine Onboarding-Vorlage. Gewichtungen, K.-o.-Kriterien und Texte sind
Vorschläge und sollten fachlich geprüft werden; alles ist in der App unter „Kataloge & Vorlagen" änderbar.

## Bekannte Grenzen

* Schema wird per `create_all` angelegt, es gibt noch keine Migrationen (z. B. Alembic).
* Nur lokale Benutzer (Rollen Administrator/Consultant); kein SSO, kein Kundenportal.
* Die PDF-Layouts sind in ReportLab umgesetzt (`backend/app/pdf_report.py`, `pdf_onboarding.py`) und lassen sich dort anpassen.
