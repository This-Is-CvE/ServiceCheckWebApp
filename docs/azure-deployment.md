# Betrieb in Azure (PaaS)

Zielbild: **Azure App Service (Linux-Container)** + **Azure Database for PostgreSQL – Flexible Server** +
**Blob Storage** für Dokumente + **Entra ID** für die Anmeldung.

> **Stand der Anleitung:** Die Anwendung selbst (Migrationen, Entra-Anmeldung per OpenID Connect, Blob-Ablage, Backup-Skripte)
> ist mit automatisierten Tests und gegen ein echtes PostgreSQL 16 geprüft. Die **`az`-Befehle unten wurden nicht gegen ein
> Azure-Abonnement ausgeführt**. Namen, SKUs und Netzwerk-Optionen bitte prüfen und an Eure Vorgaben anpassen. Die Anmeldung
> gegen Euren Entra-Mandanten ist erst bei Euch testbar.

Platzhalter: `<rg>` Ressourcengruppe, `<acr>` Container Registry, `<pg>` PostgreSQL-Servername, `<sa>` Storage-Konto,
`<app>` Web-App-Name, `<region>` z. B. `germanywestcentral`.

## 1. Image bauen und bereitstellen

```bash
az group create -n <rg> -l <region>
az acr create -g <rg> -n <acr> --sku Basic
az acr build -r <acr> -t servicecheck:1 .          # im Repository-Hauptordner
```

## 2. PostgreSQL

```bash
az postgres flexible-server create -g <rg> -n <pg> -l <region> \
  --version 16 --tier Burstable --sku-name Standard_B1ms --storage-size 32 \
  --backup-retention 35 --admin-user scadmin --admin-password '<starkes-passwort>' \
  --public-access None
az postgres flexible-server db create -g <rg> -s <pg> -d servicecheck
```

* `--backup-retention 35`: tägliche automatische Sicherungen, Wiederherstellung auf einen beliebigen Zeitpunkt der letzten
  35 Tage. Geo-redundante Sicherung lässt sich nur beim Anlegen aktivieren (`--geo-redundant-backup Enabled`), falls gewünscht.
* **Netzwerk:** `--public-access None` bedeutet, dass der Server nicht öffentlich ist. Für die Anbindung der Web-App die
  VNet-Integration der App Service mit einem privaten Zugang (VNet/Private Endpoint) einrichten. Wer es zum Testen
  einfacher will, kann die Firewall für Azure-Dienste freigeben, das ist für Produktion nicht zu empfehlen.
* Verbindungs-URL für die App (SSL ist Pflicht):
  `postgresql+psycopg://scadmin:<passwort>@<pg>.postgres.database.azure.com:5432/servicecheck?sslmode=require`

## 3. Blob Storage für Dokumente

```bash
az storage account create -g <rg> -n <sa> -l <region> --sku Standard_ZRS --allow-blob-public-access false
az storage container create --account-name <sa> -n documents --auth-mode login
az storage account blob-service-properties update -g <rg> --account-name <sa> \
  --enable-versioning true --enable-delete-retention true --delete-retention-days 30 \
  --enable-container-delete-retention true --container-delete-retention-days 30
```

Versionierung und Soft Delete sind der Schutz gegen versehentliches Löschen oder Überschreiben von Dokumenten.

## 4. Web-App

```bash
az appservice plan create -g <rg> -n plan-servicecheck --is-linux --sku B1
az webapp create -g <rg> -p plan-servicecheck -n <app> \
  --deployment-container-image-name <acr>.azurecr.io/servicecheck:1
az webapp identity assign -g <rg> -n <app>
az webapp update -g <rg> -n <app> --https-only true
```

Berechtigungen der **Managed Identity** der Web-App (Principal-ID aus dem vorherigen Befehl):

```bash
az role assignment create --assignee <principal-id> --role AcrPull --scope $(az acr show -n <acr> --query id -o tsv)
az role assignment create --assignee <principal-id> --role "Storage Blob Data Contributor" \
  --scope $(az storage account show -g <rg> -n <sa> --query id -o tsv)
az webapp config set -g <rg> -n <app> --acr-use-identity true --acr-identity '[system]'
```

Einstellungen (Geheimnisse besser als **Key-Vault-Referenz** `@Microsoft.KeyVault(SecretUri=...)` statt Klartext):

```bash
az webapp config appsettings set -g <rg> -n <app> --settings \
  WEBSITES_PORT=8000 \
  DATABASE_URL='postgresql+psycopg://scadmin:<passwort>@<pg>.postgres.database.azure.com:5432/servicecheck?sslmode=require' \
  SECRET_KEY='<mit openssl rand -hex 32 erzeugen>' \
  REPORT_COMPANY=PCO \
  STORAGE_BACKEND=azure \
  AZURE_STORAGE_ACCOUNT_URL='https://<sa>.blob.core.windows.net' \
  AZURE_STORAGE_CONTAINER=documents
```

Integritätsprüfung: Pfad `/api/health` (Portal: Web-App → Überwachung → Integritätsprüfung).

Die App legt das Datenbankschema beim Start per Migration an. Bei mehreren Instanzen verhindert eine Datenbanksperre
parallele Migrationen. **Ohne `SECRET_KEY` (und, bei aktiver lokaler Anmeldung, `ADMIN_PASSWORD`) startet die App mit
PostgreSQL absichtlich nicht.**

## 5. Anmeldung mit Entra ID

1. Entra-Admin-Center → **App-Registrierungen → Neue Registrierung**, „Nur dieses Verzeichnis“ (Einzelmandant).
   Umleitungs-URI (Typ *Web*): `https://<app>.azurewebsites.net/api/auth/oidc/callback` (bzw. Eure eigene Domain).
2. **Zertifikate & Geheimnisse → Neuer geheimer Clientschlüssel**, Wert notieren (Ablaufdatum im Kalender vermerken).
3. **App-Rollen** anlegen (zulässige Mitgliedstypen: *Benutzer/Gruppen*):
   * Wert `ServiceCheck.Admin` (pflegt Kataloge, Vorlagen, Benutzer)
   * Wert `ServiceCheck.Consultant` (führt Checks und Onboardings durch)
4. **Unternehmensanwendungen → die App → Eigenschaften → „Zuweisung erforderlich“ = Ja**, danach unter
   *Benutzer und Gruppen* Eure Sicherheitsgruppen den Rollen zuweisen.
5. Einstellungen der Web-App ergänzen:

```bash
az webapp config appsettings set -g <rg> -n <app> --settings \
  OIDC_TENANT_ID=<verzeichnis-id> OIDC_CLIENT_ID=<anwendungs-id> OIDC_CLIENT_SECRET='<geheimer-schluessel>' \
  OIDC_REDIRECT_URI='https://<app>.azurewebsites.net/api/auth/oidc/callback'
```

Rollen und Namen werden bei **jeder Anmeldung** aus Entra übernommen. Wer die Rolle verliert, kann sich nicht mehr
anmelden. Ein bereits ausgestelltes Anwendungs-Token bleibt bis zu `TOKEN_HOURS` (Standard 12 h) gültig.
Wer sofort gesperrt werden soll, wird zusätzlich in der App unter „Benutzer“ deaktiviert.

**Empfohlene Reihenfolge:** Erst mit `AUTH_LOCAL_ENABLED=1` (Standard, `ADMIN_PASSWORD` gesetzt) starten, die
Microsoft-Anmeldung mit einem Administrator testen und danach `AUTH_LOCAL_ENABLED=0` setzen. Bei abgeschalteter lokaler
Anmeldung legt die App keinen Standard-Administrator mehr an.

## 6. Datensicherung

| Was | Wie | Aufbewahrung |
|---|---|---|
| Datenbank (Stammdaten, Checks, Onboardings, Katalog) | automatische Sicherung des Flexible Servers, Wiederherstellung auf Zeitpunkt | bis 35 Tage (Einstellung `--backup-retention`) |
| Dokumente (PDFs) | Blob-Versionierung und Soft Delete | 30 Tage nach Löschen (Einstellung oben) |
| Zusätzliche, unabhängige Kopie der Datenbank (optional) | `scripts/backup.sh` (pg_dump), z. B. wöchentlich von einer VM oder einem Automation-Job in ein **separates** Storage-Konto | frei wählbar |
| Entra-Rollenzuweisungen | liegen in Entra ID, nicht in der App-Datenbank | – |

**Wiederherstellung der Datenbank (zeitpunktgenau):**

```bash
az postgres flexible-server restore -g <rg> -n <pg>-restore --source-server <pg> --restore-time "2026-10-09T08:00:00Z"
```

Das legt einen **neuen** Server an. Danach `DATABASE_URL` der Web-App auf den neuen Server umstellen (oder Daten gezielt
übernehmen). Nach einer Wiederherstellung auf einen früheren Stand können Dokument-Blobs existieren, die in der Datenbank
nicht mehr referenziert sind, sowie umgekehrt Datenbankeinträge ohne Blob, wenn das Blob nach dem gewählten Zeitpunkt
gelöscht wurde. Blob-Versionen und Soft Delete helfen beim Zurückholen. Plant dafür bei einem Notfall etwas Zeit ein.

**Wiederherstellung aus einem `pg_dump`:** `PGURL=... ./scripts/restore.sh <datei>.dump` in eine leere Datenbank.
Dieser Weg ist hier mit einem echten Rückspieltest geprüft.

**Mindestens einmal vor dem Produktivstart** eine Wiederherstellung real durchspielen (Datenbank auf neuen Server,
Dokument aus Soft Delete zurückholen). Eine Sicherung, die nie zurückgespielt wurde, ist keine.

## 7. Updates einspielen

```bash
az acr build -r <acr> -t servicecheck:2 .
az webapp config container set -g <rg> -n <app> --container-image-name <acr>.azurecr.io/servicecheck:2
```

Datenbankänderungen laufen beim Start als Migration. Vor größeren Änderungen vorher eine manuelle Sicherung
(`scripts/backup.sh`) erstellen.

## 8. Noch nicht enthalten

* Änderungsprotokoll (wer hat wann was geändert) und Sperre nach Fehlversuchen bei der lokalen Anmeldung.
* Automatisches Aufräumen von Blobs ohne Datenbankverweis.
* Infrastruktur als Code (Bicep/Terraform) und eine CI/CD-Pipeline.
