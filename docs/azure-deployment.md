# Service Check in Azure bereitstellen – Schritt für Schritt

Ziel: Die App läuft mit PostgreSQL als Datenbank, Dokumenten im Blob Storage und Anmeldung über Entra ID.

| Baustein | Azure-Dienst |
|---|---|
| Anwendung (Container) | Azure App Service für Linux |
| Container-Image | Azure Container Registry (das Image wird **in Azure** gebaut, Docker auf Deinem Rechner ist nicht nötig) |
| Datenbank | Azure Database for PostgreSQL – Flexible Server |
| Dokumente (PDFs) | Azure Blob Storage |
| Anmeldung | Microsoft Entra ID |

> **Was geprüft ist und was nicht:** Die Anwendung (Migrationen, Entra-Anmeldung, Blob-Ablage, Backup-Skripte) ist mit
> automatisierten Tests geprüft, auch gegen ein echtes PostgreSQL 16. Jeden `az`-Befehl dieser Anleitung habe ich gegen die
> Azure-CLI abgeglichen (Befehle und Parameter existieren). **Ausgeführt gegen ein Azure-Abonnement habe ich sie nicht.**
> Plant für den ersten Durchlauf Zeit ein. Wenn ein Schritt eine Fehlermeldung liefert, steht am Ende ein Abschnitt zur Fehlersuche.
>
> **Kosten:** Alle Ressourcen verursachen laufende Kosten. Prüft die Preise im Azure-Preisrechner. Wenn Ihr nur testen wollt, löscht
> alles am Ende wieder (Abschnitt „Aufräumen“).

---

## Schritt 0 – Was Du brauchst

- Ein **Azure-Abonnement** und dort die Rolle **Besitzer** (oder *Mitwirkender* plus *Benutzerzugriffsadministrator*) auf der
  Ressourcengruppe. Rollenzuweisungen für die Managed Identity in Schritt 7 brauchen diese Rechte.
- Für Schritt 9 (Entra-App-Registrierung) Rechte im Entra-Admin-Center, z. B. die Rolle *Anwendungsentwickler* oder
  *Cloudanwendungsadministrator*. Wenn Du sie nicht hast, schick Deiner IT die Beschreibung aus Schritt 9.
- Auf Deinem Rechner: **Git Bash** (hast Du schon), die **Azure-CLI** und `openssl` (ist in Git Bash dabei).
- Das Projekt als Ordner auf Deinem Rechner (`~/ServiceCheckWebApp`) mit dem aktuellen Stand (`git pull`).

## Schritt 1 – Azure-CLI installieren und anmelden

Installation unter Windows (PowerShell oder Eingabeaufforderung, einmalig; danach Git Bash neu öffnen):

```
winget install -e --id Microsoft.AzureCLI
```

In Git Bash:

```bash
az login
az account list --output table
az account set --subscription "<Name oder ID Deines Abonnements>"
az account show --query "{Abo:name, Mandant:tenantId}" --output table
```

Notiere Dir die **Mandanten-ID** (`tenantId`), Du brauchst sie in Schritt 9.

## Schritt 2 – Namen und Geheimnisse festlegen

Alle folgenden Befehle benutzen diese Variablen. **Setze sie in jedem neuen Terminal erneut**, am besten, indem Du den Block in eine
Datei `azure.env` außerhalb des Projekts (oder im Projekt, sie ist per `.gitignore` ausgeschlossen) speicherst und mit
`source azure.env` lädst.

```bash
export MSYS_NO_PATHCONV=1               # Git Bash unter Windows: verhindert, dass "/api/health" & Co. umgeschrieben werden

SUFFIX=pco1                             # kurz, nur Kleinbuchstaben/Ziffern, max. 6 Zeichen; macht die Namen weltweit eindeutig
RG=rg-servicecheck
LOC=germanywestcentral
ACR=acrservicecheck$SUFFIX              # nur Kleinbuchstaben/Ziffern
PG=pg-servicecheck-$SUFFIX
SA=stservicecheck$SUFFIX                # Speicherkonto: 3–24 Zeichen, nur Kleinbuchstaben/Ziffern
PLAN=plan-servicecheck
APP=app-servicecheck-$SUFFIX            # die Adresse wird https://$APP.azurewebsites.net
DBNAME=servicecheck
PGADMIN=scadmin

PGPASS=$(openssl rand -hex 16)          # nur Hex-Zeichen: keine Sonderzeichen, die in der Datenbank-URL Probleme machen
SECRET_KEY=$(openssl rand -hex 32)      # signiert die Anmelde-Token der App
ADMIN_PASSWORD='<Dein starkes Passwort für den ersten Administrator>'

echo "PGPASS=$PGPASS"; echo "SECRET_KEY=$SECRET_KEY"   # JETZT in einen Passwort-Manager kopieren
```

> **Wichtig, wenn Du das Terminal später neu öffnest:** `source azure.env` setzt `PGPASS` und `SECRET_KEY` dann auf **neue Zufallswerte**.
> `SECRET_KEY` darf sich ändern, `PGPASS` aber **nicht**: Es muss dem Passwort entsprechen, mit dem der Datenbankserver angelegt wurde. Hast Du
> den alten Wert nicht mehr, setze das Datenbank-Passwort auf den aktuellen Wert zurück (nach Schritt 5):
> `az postgres flexible-server update --resource-group $RG --name $PG --admin-password "$PGPASS"`
>
> Schreibe `PGPASS`, `SECRET_KEY` und `ADMIN_PASSWORD` in Euren Passwort-Manager. Danach brauchst Du sie nur noch, wenn Du Dich
> direkt mit der Datenbank verbinden willst (`PGPASS`). Wenn Du `SECRET_KEY` änderst, werden alle angemeldeten Nutzer abgemeldet.

## Schritt 3 – Ressourcengruppe anlegen

```bash
az group create --name $RG --location $LOC
```

Bei einem neuen Abonnement müssen einige Dienste einmalig registriert werden. Falls ein späterer Schritt
`MissingSubscriptionRegistration` meldet, führe aus:

```bash
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.DBforPostgreSQL
az provider register --namespace Microsoft.Web
az provider register --namespace Microsoft.Storage
```

## Schritt 4 – Container Registry anlegen und das Image bauen

```bash
az acr create --resource-group $RG --name $ACR --sku Basic
```

Dann **im Projektordner** (dort liegt die `Dockerfile`) das Image in Azure bauen lassen. Dieser Schritt lädt Basis-Images aus
Azure heraus, Dein Docker-Hub-Problem spielt hier keine Rolle:

```bash
cd ~/ServiceCheckWebApp
az acr build --registry $ACR --image servicecheck:1 --file Dockerfile .
```

Der Build dauert einige Minuten. Am Ende steht `Run ID: ... was successful`.

> Auf manchen Test- und kostenlosen Abonnements sind *ACR Tasks* gesperrt. Dann meldet der Befehl einen Fehler. Alternativ
> baust Du lokal mit Docker (`docker build -t $ACR.azurecr.io/servicecheck:1 .`), meldest Dich mit `az acr login --name $ACR` an
> und lädst mit `docker push $ACR.azurecr.io/servicecheck:1` hoch. Das braucht funktionierendes Docker.

Prüfen:

```bash
az acr repository list --name $ACR --output table
```

## Schritt 5 – PostgreSQL anlegen

```bash
az postgres flexible-server create \
  --resource-group $RG --name $PG --location $LOC \
  --version 16 --tier Burstable --sku-name Standard_B1ms --storage-size 32 \
  --backup-retention 35 --geo-redundant-backup Disabled \
  --admin-user $PGADMIN --admin-password $PGPASS \
  --public-access 0.0.0.0 --yes

az postgres flexible-server db create --resource-group $RG --server-name $PG --name $DBNAME
```

Das dauert einige Minuten. Was die Einstellungen bedeuten:

- `--backup-retention 35`: Azure sichert automatisch täglich und ermöglicht die Wiederherstellung auf einen beliebigen Zeitpunkt der
  letzten 35 Tage. `--geo-redundant-backup Enabled` legt zusätzlich eine Kopie in einer anderen Region ab, lässt sich aber nur
  **beim Anlegen** festlegen. Entscheide das jetzt.
- `--public-access 0.0.0.0` legt die Firewall-Regel „Azure-Dienste zulassen“ an. Der Server hat einen **öffentlichen Endpunkt**
  (`<name>.postgres.database.azure.com`) und bekommt **keine IP aus einem virtuellen Netz**. Die Regel erlaubt Verbindungen von
  **jeder** Azure-Ressource, auch von Ressourcen anderer Azure-Kunden. Geschützt bist Du dann durch Benutzername, Passwort und die
  erzwungene SSL-Verschlüsselung, nicht durch das Netzwerk. Für den ersten Start ist das ein üblicher Kompromiss. Strenger geht es mit
  **Schritt 8b** (nur die Adressen Deiner Web-App) oder mit privatem Zugang (siehe unten und [azure-deployment-private.md](azure-deployment-private.md)). SSL ist bei Flexible Server standardmäßig Pflicht.
- Gibt es für `Standard_B1ms` in Eurer Region keine Kapazität, wählt eine andere Region oder ein anderes SKU. `az postgres
  flexible-server list-skus --location $LOC` zeigt die möglichen Größen.
- **Privater Zugang:** Wollt Ihr den Server ohne öffentlichen Endpunkt betreiben (private IP in einem virtuellen Netz, Web-App und Dokumentenspeicher
  ebenfalls nur privat erreichbar), folgt Ihr stattdessen der Anleitung **[azure-deployment-private.md](azure-deployment-private.md)**. Sie ersetzt die Schritte 5,
  7c bis 8b. Der Netzwerkmodus wird beim Anlegen des Servers gewählt und lässt sich nach meinem Kenntnisstand nachträglich nicht umstellen. Entscheidet das also vor Schritt 5.

Die Datenbank-URL, die die App später braucht, setzt sich so zusammen:

```bash
DATABASE_URL="postgresql+psycopg://$PGADMIN:$PGPASS@$PG.postgres.database.azure.com:5432/$DBNAME?sslmode=require"
```

## Schritt 6 – Speicherkonto für Dokumente

```bash
az storage account create \
  --resource-group $RG --name $SA --location $LOC \
  --sku Standard_LRS --allow-blob-public-access false --min-tls-version TLS1_2

az storage container create --account-name $SA --name documents --auth-mode login

az storage account blob-service-properties update \
  --resource-group $RG --account-name $SA \
  --enable-versioning true \
  --enable-delete-retention true --delete-retention-days 30 \
  --enable-container-delete-retention true --container-delete-retention-days 30
```

- `Standard_LRS` hält drei Kopien in einem Rechenzentrum. Für mehr Ausfallsicherheit nehmt `Standard_ZRS` (Zonen) oder
  `Standard_GRS` (zweite Region), sofern die Region das anbietet.
- **Versionierung und „Soft Delete“** schützen vor versehentlichem Löschen oder Überschreiben. Gelöschte Dokumente lassen sich
  30 Tage lang zurückholen.
- Der Befehl `az storage container create` kann mit „Berechtigung fehlt“ scheitern, wenn Dein Konto keine Datenrolle hat.
  Dann gib Dir selbst die Rolle *Storage Blob Data Contributor* auf dem Speicherkonto (Portal: Speicherkonto → Zugriffssteuerung (IAM)).

## Schritt 7 – Web-App anlegen und konfigurieren

**7a – Plan und Web-App mit Managed Identity:**

```bash
az appservice plan create --resource-group $RG --name $PLAN --is-linux --sku B1 --location $LOC

az webapp create --resource-group $RG --plan $PLAN --name $APP \
  --container-image-name $ACR.azurecr.io/servicecheck:1 \
  --assign-identity '[system]'

az webapp update --resource-group $RG --name $APP --https-only true
az webapp config set --resource-group $RG --name $APP --always-on true --min-tls-version 1.2 --ftps-state Disabled
```

**7b – Rechte für die Managed Identity** (die App braucht keine Passwörter für Registry und Dokumentenspeicher):

```bash
PRINCIPAL=$(az webapp identity show --resource-group $RG --name $APP --query principalId --output tsv)
ACR_ID=$(az acr show --name $ACR --query id --output tsv)
SA_ID=$(az storage account show --resource-group $RG --name $SA --query id --output tsv)

az role assignment create --assignee-object-id $PRINCIPAL --assignee-principal-type ServicePrincipal --role AcrPull --scope $ACR_ID
az role assignment create --assignee-object-id $PRINCIPAL --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" --scope $SA_ID

az webapp config set --resource-group $RG --name $APP --acr-use-identity true --acr-identity '[system]'
```

Rollenzuweisungen brauchen bis zu ein paar Minuten, bis sie wirken.

**7c – Einstellungen der App:**

Prüfe vorher, dass **alle** Variablen gefüllt sind. Eine leere Variable wird sonst als leere App-Einstellung gespeichert, und die App startet
nicht (Meldung `DATABASE_URL ist leer oder ungültig`):

```bash
DATABASE_URL="postgresql+psycopg://$PGADMIN:$PGPASS@$PG.postgres.database.azure.com:5432/$DBNAME?sslmode=require"
for v in DATABASE_URL SECRET_KEY ADMIN_PASSWORD PGPASS SA APP RG; do [ -z "${!v}" ] && echo "FEHLT: $v"; done; echo "Prüfung beendet"
```

Steht nach „Prüfung beendet“ **kein** `FEHLT:` davor, kannst Du weitermachen.

```bash
az webapp config appsettings set --resource-group $RG --name $APP --settings \
  WEBSITES_PORT=8000 \
  DATABASE_URL="$DATABASE_URL" \
  SECRET_KEY="$SECRET_KEY" \
  ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  REPORT_COMPANY=PCO \
  STORAGE_BACKEND=azure \
  AZURE_STORAGE_ACCOUNT_URL="https://$SA.blob.core.windows.net" \
  AZURE_STORAGE_CONTAINER=documents \
  SEED_DEMO_DATA=0
```

(`SEED_DEMO_DATA=1` legt zum Testen einen Beispielkatalog an, sofern noch gar kein Managed Service existiert.)

**7d – Protokolle einschalten und App neu starten:**

```bash
az webapp log config --resource-group $RG --name $APP --docker-container-logging filesystem
az webapp restart --resource-group $RG --name $APP
```

## Schritt 8 – Prüfen, ob die App läuft

Der erste Start dauert 2 bis 5 Minuten (Image laden, Datenbank-Migration). Dann:

```bash
echo "https://$APP.azurewebsites.net"
curl https://$APP.azurewebsites.net/api/health
```

Erwartet: `{"status":"ok"}`. Öffne die Adresse im Browser und melde Dich mit **`admin`** und Deinem `ADMIN_PASSWORD` an.

Läuft sie nicht, siehe Protokoll:

```bash
az webapp log tail --resource-group $RG --name $APP
```

Typische Meldungen und ihre Ursache stehen im Abschnitt „Fehlersuche“.

**Dokument-Ablage testen:** Lege einen Kunden und ein Onboarding an, klicke auf „PDF ablegen“ und lade das Dokument wieder herunter.
Danach sollte im Portal unter Speicherkonto → Container `documents` ein Blob unter `onboardings/…` liegen.

Optional (empfohlen): Im Portal unter Web-App → Überwachung → **Integritätsprüfung** den Pfad `/api/health` eintragen,
damit Azure eine hängende Instanz erkennt.

## Schritt 8b – Datenbankzugriff auf die Web-App beschränken (empfohlen)

Statt „alle Azure-Ressourcen“ erlaubst Du nur die ausgehenden Adressen Deiner Web-App. Erst die neuen Regeln anlegen, dann die
allgemeine Regel löschen:

```bash
# 1) Für jede mögliche ausgehende Adresse der Web-App eine Regel anlegen
for ip in $(az webapp show --resource-group $RG --name $APP --query possibleOutboundIpAddresses --output tsv | tr ',' ' '); do
  az postgres flexible-server firewall-rule create --resource-group $RG --server-name $PG \
    --name "app-${ip//./-}" --start-ip-address $ip --end-ip-address $ip
done

# 2) Die allgemeine Azure-Regel (0.0.0.0) suchen und löschen
RULE=$(az postgres flexible-server firewall-rule list --resource-group $RG --server-name $PG \
  --query "[?startIpAddress=='0.0.0.0'].name" --output tsv)
az postgres flexible-server firewall-rule delete --resource-group $RG --server-name $PG --name "$RULE" --yes

# 3) Prüfen, dass die App weiter läuft
curl https://$APP.azurewebsites.net/api/health
```

Die ausgehenden Adressen können sich ändern, wenn Du den App-Service-Plan skalierst oder auf eine andere Preisstufe wechselst. Wiederhole dann
Punkt 1. Die Liste `possibleOutboundIpAddresses` enthält alle Adressen, die die App nutzen kann. Meldet die App danach Datenbank-Fehler,
legst Du die allgemeine Regel mit `--start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0` wieder an.

## Schritt 9 – Anmeldung mit Entra ID einrichten

Diese Schritte erfolgen im **Entra-Admin-Center** (https://entra.microsoft.com), nicht in der Konsole. Wenn Du keine Rechte hast, gib
sie Deiner IT mit.

1. **Identität → Anwendungen → App-Registrierungen → Neue Registrierung.**
   - Name: `Service Check`
   - Unterstützte Kontotypen: **Nur Konten in diesem Organisationsverzeichnis** (Einzelmandant)
   - Umleitungs-URI: Plattform **Web**, Wert `https://<APP>.azurewebsites.net/api/auth/oidc/callback` (mit Deinem App-Namen)
   - **Registrieren**
2. Auf der Übersichtsseite notierst Du **Anwendungs-ID (Client)** und **Verzeichnis-ID (Mandant)**.
3. **Zertifikate & Geheimnisse → Neuer geheimer Clientschlüssel.** Ablauf 12 oder 24 Monate wählen. Den **Wert** sofort kopieren,
   er wird nur einmal angezeigt. Trage das Ablaufdatum in einen Kalender ein. Danach ist die Anmeldung kaputt, bis ein neuer
   Schlüssel in der App hinterlegt ist.
4. **App-Rollen → App-Rolle erstellen** (zweimal):

   | Anzeigename | Zulässige Mitgliedstypen | Wert | Beschreibung |
   |---|---|---|---|
   | Service Check Administrator | Benutzer/Gruppen | `ServiceCheck.Admin` | Pflegt Kataloge, Vorlagen und Benutzer |
   | Service Check Consultant | Benutzer/Gruppen | `ServiceCheck.Consultant` | Führt Service Checks und Onboardings durch |

5. **Unternehmensanwendungen → Service Check → Eigenschaften:** **„Zuweisung erforderlich?“ = Ja**, speichern. Dann kann sich nur
   anmelden, wer zugewiesen ist.
6. **Unternehmensanwendungen → Service Check → Benutzer und Gruppen → Benutzer/Gruppe hinzufügen:** Benutzer oder Gruppen auswählen
   und jeweils eine Rolle zuweisen. (Gruppen lassen sich nur mit einer Entra-ID-P1/P2-Lizenz zuweisen, sonst einzelne Benutzer.)
   Weise **Dir selbst** zuerst `Service Check Administrator` zu.
7. Zurück in Git Bash die Werte in der App hinterlegen:

```bash
TENANT_ID="<Verzeichnis-ID aus Schritt 2>"
CLIENT_ID="<Anwendungs-ID aus Schritt 2>"
CLIENT_SECRET="<Wert des Clientschlüssels aus Schritt 3>"

az webapp config appsettings set --resource-group $RG --name $APP --settings \
  OIDC_TENANT_ID="$TENANT_ID" \
  OIDC_CLIENT_ID="$CLIENT_ID" \
  OIDC_CLIENT_SECRET="$CLIENT_SECRET" \
  OIDC_REDIRECT_URI="https://$APP.azurewebsites.net/api/auth/oidc/callback"

az webapp restart --resource-group $RG --name $APP
```

Danach steht auf der Anmeldeseite **„Mit Microsoft anmelden“**. Melde Dich damit an. Unter „Benutzer“ erscheint Dein Konto mit dem Hinweis
**SSO**. Rolle und Name kommen ab sofort aus Entra und werden bei jeder Anmeldung aktualisiert.

## Schritt 10 – Lokale Anmeldung abschalten (empfohlen)

Erst wenn die Microsoft-Anmeldung als Administrator funktioniert:

```bash
az webapp config appsettings set --resource-group $RG --name $APP --settings AUTH_LOCAL_ENABLED=0
az webapp restart --resource-group $RG --name $APP
```

Ab dann gibt es keine Passwort-Anmeldung mehr. Ein verlorenes `ADMIN_PASSWORD` ist kein Risiko mehr. Wenn die Entra-Anmeldung einmal
nicht funktioniert, setzt Du `AUTH_LOCAL_ENABLED=1` wieder und meldest Dich als `admin` an. Das geht aber nur, wenn die lokale Anmeldung
mindestens einmal aktiv war (Standard-Administrator wird beim allerersten Start angelegt).

## Schritt 11 – Datensicherung prüfen und Wiederherstellung üben

**Was gesichert wird:**

| Was | Wie | Aufbewahrung |
|---|---|---|
| Datenbank | automatische Sicherung des Flexible Servers, Wiederherstellung auf Zeitpunkt | 35 Tage (Schritt 5) |
| Dokumente (PDFs) | Blob-Versionierung und Soft Delete | 30 Tage nach dem Löschen (Schritt 6) |
| Entra-Rollenzuweisungen | liegen in Entra ID, nicht in der App | – |
| Optional: unabhängige Kopie der Datenbank | `scripts/backup.sh` (pg_dump) in ein **anderes** Speicherkonto | frei wählbar |

Einstellung prüfen:

```bash
az postgres flexible-server show --resource-group $RG --name $PG --query backup
```

**Wiederherstellung der Datenbank üben** (vor dem Produktivstart einmal, danach z. B. halbjährlich):

```bash
az postgres flexible-server restore \
  --resource-group $RG --name $PG-restore --source-server $PG \
  --restore-time "2026-10-12T08:00:00Z"
```

Das legt einen **neuen** Server `$PG-restore` mit dem Stand zu diesem Zeitpunkt (UTC) an. Der Zeitpunkt muss in der Vergangenheit und innerhalb der
Aufbewahrungszeit liegen. Um die App darauf umzustellen, setzt Du `DATABASE_URL` auf den neuen Servernamen und startest neu. Den
Übungsserver löschst Du danach wieder (`az postgres flexible-server delete --resource-group $RG --name $PG-restore --yes`).

**Gelöschtes Dokument zurückholen:**

```bash
az storage blob undelete --account-name $SA --container-name documents --name "onboardings/<ID>/<Datei>.pdf" --auth-mode login
```

Den Blob-Namen findest Du im Portal unter Speicherkonto → Container `documents` (Ansicht „Gelöschte Blobs anzeigen“).

**Wichtig:** Nach einer zeitpunktgenauen Wiederherstellung der Datenbank können Dokument-Blobs existieren, die in der Datenbank nicht
mehr referenziert sind, oder Datenbankeinträge ohne Blob, wenn das Blob nach dem gewählten Zeitpunkt gelöscht wurde. Blob-Versionen
und Soft Delete helfen beim Zurückholen.

## Schritt 12 – Updates einspielen

Neuen Stand holen, neues Image bauen, App darauf umstellen:

```bash
cd ~/ServiceCheckWebApp && git pull
az acr build --registry $ACR --image servicecheck:2 --file Dockerfile .
az webapp config container set --resource-group $RG --name $APP --container-image-name $ACR.azurecr.io/servicecheck:2
az webapp restart --resource-group $RG --name $APP
```

Datenbankänderungen laufen beim Start automatisch als Migration. Erhöhe das Tag (`:2`, `:3`, …) bei jedem Update, damit klar ist, was läuft und
Du bei Problemen auf das vorherige Tag zurückstellen kannst. **Vor größeren Updates** zusätzlich eine Datenbanksicherung machen
(`scripts/backup.sh`, siehe README) oder wenigstens den Wiederherstellungszeitpunkt notieren.

---

## Fehlersuche

| Symptom | Mögliche Ursache und Abhilfe |
|---|---|
| `MissingSubscriptionRegistration` | Dienst-Registrierung fehlt, siehe Schritt 3 |
| `acr build` bricht mit `sh: tsc: Permission denied` (Exit 126) ab | Das lokale `node_modules` aus Windows wurde ins Image kopiert und hat das Ausführrecht von `tsc` verloren. Mit dem aktuellen Stand nicht mehr möglich (`git pull`, danach `acr build` wiederholen) |
| `acr build` schlägt fehl mit Hinweis auf Tasks | ACR Tasks im Abonnement gesperrt, Alternative in Schritt 4 |
| Name „bereits vergeben“ (ACR, Speicherkonto, Server, Web-App) | `SUFFIX` ändern und Schritt 2 wiederholen |
| Web-App zeigt „Application Error“ oder 503 | `az webapp log tail`. Meist: Image konnte nicht geladen werden (Rolle `AcrPull` noch nicht wirksam, dann neu starten) oder falsche Einstellungen |
| Log: `DATABASE_URL ist leer oder ungültig` (ältere Version: `Could not parse SQLAlchemy URL`) | Die Einstellung `DATABASE_URL` ist leer oder falsch aufgebaut. Variablen prüfen und Schritt 7c wiederholen. Eingestellte Werte ansehen (ohne Geheimnisse): `az webapp config appsettings list --resource-group $RG --name $APP --query "[].{name:name, laenge:length(value)}" --output table`. Eine Länge von 0 bedeutet leer |
| Log: `SECRET_KEY muss gesetzt sein und mindestens 32 Zeichen haben` oder `ADMIN_PASSWORD muss gesetzt sein` | Einstellung fehlt oder ist zu kurz, Schritt 7c wiederholen. Mit PostgreSQL startet die App sonst absichtlich nicht (`ADMIN_PASSWORD` wird nur beim allerersten Start geprüft) |
| Log: `password authentication failed` | `PGPASS` stimmt nicht mit dem Passwort des Datenbankservers überein, siehe Hinweis in Schritt 2 (Passwort zurücksetzen) |
| Log: Verbindungsfehler zur Datenbank / `timeout` | Die Firewall lässt die App nicht durch (nach Schritt 8b: neue ausgehende Adresse der Web-App fehlt, Schritt 8b Punkt 1 wiederholen). `DATABASE_URL` prüfen (Servername, Passwort, `?sslmode=require`). Server gestartet? |
| Log: `Die Datenbank enthält Tabellen, wurde aber nicht mit Migrationen angelegt` | Es liegt eine Datenbank aus einer sehr alten Version vor. Neue, leere Datenbank verwenden |
| Dokument ablegen oder herunterladen schlägt fehl (503 „Dokumentenspeicher“) | Rolle *Storage Blob Data Contributor* der Managed Identity fehlt oder noch nicht wirksam (Schritt 7b), oder `AZURE_STORAGE_ACCOUNT_URL` falsch |
| Anmeldeseite: „Für dieses Konto ist keine Rolle vergeben“ | Benutzer ist in Entra keiner App-Rolle zugewiesen (Schritt 9.6) |
| Anmeldeseite: „Die Antwort von Microsoft konnte nicht überprüft werden“ / „Anmeldung bei Microsoft fehlgeschlagen“ | `OIDC_TENANT_ID`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` falsch, Clientschlüssel abgelaufen oder Umleitungs-URI weicht ab |
| Microsoft meldet `AADSTS50011` (Antwort-URL stimmt nicht überein) | Die Umleitungs-URI in der App-Registrierung und `OIDC_REDIRECT_URI` müssen **exakt** gleich sein (Schreibweise, `https`) |
| Microsoft meldet `AADSTS50105` (Benutzer nicht zugewiesen) | Weil „Zuweisung erforderlich“ = Ja: Benutzer der App zuweisen |
| Kein Button „Mit Microsoft anmelden“ | Eine der vier `OIDC_…`-Einstellungen fehlt. Prüfen: `https://$APP.azurewebsites.net/api/auth/config` muss `"oidc":true` zeigen |

## Aufräumen (alles wieder löschen)

Löscht **alle** Ressourcen der Gruppe unwiderruflich, inklusive Datenbank und Dokumente:

```bash
az group delete --name $RG --yes --no-wait
```

Die App-Registrierung in Entra bleibt bestehen und muss dort separat gelöscht werden.

## Empfohlene nächste Schritte für den Dauerbetrieb

- Datenbank ohne öffentlichen Endpunkt (virtuelles Netzwerk bzw. privater Endpunkt, siehe Schritt 5) und einen eigenen Datenbankbenutzer mit eingeschränkten Rechten statt
  des Server-Administrators.
- Geheimnisse (`SECRET_KEY`, `DATABASE_URL`, `OIDC_CLIENT_SECRET`) in einem **Key Vault** ablegen und per Key-Vault-Referenz in die App-Einstellungen einbinden.
- Eigene Domain mit Zertifikat. Danach `OIDC_REDIRECT_URI` und die Umleitungs-URI in Entra anpassen.
- Warnungen (Azure Monitor) für ausgefallene Integritätsprüfung, Datenbank-Speicher und ablaufenden Clientschlüssel.
- Die Ressourcen als Code (Bicep oder Terraform) und eine Pipeline für Updates.
- Zusätzliche, unabhängige Datenbanksicherung (`scripts/backup.sh`) in ein separates Speicherkonto oder Abonnement.
