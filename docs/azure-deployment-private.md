# Service Check in Azure – Variante mit privatem Netzwerk

Diese Anleitung ersetzt in der Hauptanleitung ([azure-deployment.md](azure-deployment.md)) die Schritte 5, 7c bis 8b und ergänzt das Netzwerk.
Ergebnis: Datenbank, Dokumentenspeicher **und die Web-App** haben keinen öffentlichen Zugang mehr. Erreichbar ist alles nur über ein
virtuelles Netz in Azure und das daran angebundene Firmennetz.

```
Firmennetz ──(VPN/Peering, Eure IT)──► virtuelles Netz  10.20.0.0/16
                                        ├─ snet-pe   Private Endpoints: Web-App (Eingang), Blob Storage
                                        ├─ snet-app  VNet-Integration der Web-App (ausgehend)
                                        └─ snet-db   PostgreSQL (private IP)
Öffentlich bleiben nur: Container Registry (Images ohne Personendaten) und die Azure-Verwaltung (az, Portal).
```

> **Geprüft und nicht geprüft:** Jeden `az`-Befehl habe ich gegen die Azure-CLI abgeglichen (Befehle und Parameter existieren). Ausgeführt
> gegen ein Azure-Abonnement habe ich ihn nicht. Am anfälligsten sind **Namensauflösung (DNS)** und die **Anbindung Eures Firmennetzes**.
> Beides hängt von Eurer Umgebung ab, deshalb gibt es unten Prüfschritte und eine Fehlersuche. Am Code der App ändert sich nichts.

## Was sich gegenüber der öffentlichen Variante ändert

| Baustein | Öffentlich (Hauptanleitung) | Privat (diese Anleitung) |
|---|---|---|
| Netzwerk | keins | neues virtuelles Netz mit drei Subnetzen |
| PostgreSQL | öffentlicher Endpunkt, Firewall-Regel | **private IP**, kein öffentlicher Zugang, private DNS-Zone |
| Web-App ausgehend | direkt | **VNet-Integration** (Datenbank und Blob nur über das Netz) |
| Blob Storage | öffentlicher Endpunkt | **Private Endpoint**, öffentlicher Zugang aus |
| Web-App eingehend | öffentlich per HTTPS | **Private Endpoint**, öffentlicher Zugang aus |
| Container Registry | öffentlich | bleibt öffentlich (ein privater Zugang braucht die Premium-Stufe) |
| Firewall-Regeln der Datenbank (Schritt 8b) | optional | entfallen |
| Verwaltung (`az`, `acr build`) | von überall | unverändert, läuft über die Azure-Verwaltungsschnittstelle |
| Logs ansehen (`az webapp log tail`, Portal-Logstream) | von überall | **nur noch aus dem Netz** (siehe Schritt P11) |

## Was Du vorher klären musst

- **Adressbereich:** `10.20.0.0/16` ist ein Vorschlag. Der Bereich darf sich **nicht** mit Eurem Firmennetz oder anderen angebundenen Netzen
  überschneiden. Frage Eure IT, bevor Du das Netz anlegst. Der Bereich lässt sich später nur mühsam ändern.
- **Anbindung des Firmennetzes und DNS:** Wie kommen die Arbeitsplätze zum virtuellen Netz (Site-to-Site-VPN, ExpressRoute, Peering zu einem
  vorhandenen Hub, oder VPN pro Benutzer) und wie lösen sie den Namen der App auf (Schritt P10)? **Das ist die größte Abhängigkeit.** Ohne diese
  Anbindung kann niemand die App aufrufen, nachdem der öffentliche Zugang abgeschaltet ist.
- **Rechte:** Du brauchst Rechte für Netzwerkressourcen und private DNS-Zonen (z. B. *Mitwirkender* auf der Ressourcengruppe; für Subnetz-Delegierungen
  ist die Rolle *Netzwerkmitwirkender* üblich).
- **Region:** Virtuelles Netz, App-Service-Plan, Datenbank und Speicherkonto müssen in **derselben Region** liegen (`$LOC`).

## Ausgangslage

Die Schritte 1 bis 4, 6, 7a und 7b der Hauptanleitung sind erledigt (Anmeldung, Variablen, Ressourcengruppe, Registry mit Image, Speicherkonto,
Web-App mit Managed Identity und Rollen). **Schritt 5 (öffentliche PostgreSQL), 7c, 7d, 8 und 8b** überspringst Du. Hast Du die öffentliche
Datenbank schon angelegt, löschst Du sie. Der Netzwerkmodus lässt sich nach meinem Kenntnisstand nachträglich nicht umstellen, und es sind nur Testdaten drin:

```bash
az postgres flexible-server delete --resource-group $RG --name $PG --yes
```

## Schritt P1 – Zusätzliche Variablen

Zu den Variablen aus Schritt 2 der Hauptanleitung kommen diese hinzu (in `azure.env` ergänzen):

```bash
VNET=vnet-servicecheck
VNET_CIDR=10.20.0.0/16                      # mit der IT abstimmen!
SNET_DB=snet-db;   SNET_DB_CIDR=10.20.1.0/24
SNET_APP=snet-app; SNET_APP_CIDR=10.20.2.0/24
SNET_PE=snet-pe;   SNET_PE_CIDR=10.20.3.0/24
ZONE_PG=servicecheck.private.postgres.database.azure.com   # muss auf .private.postgres.database.azure.com enden
ZONE_BLOB=privatelink.blob.core.windows.net
ZONE_APP=privatelink.azurewebsites.net
```

## Schritt P2 – Virtuelles Netz und Subnetze

```bash
az network vnet create --resource-group $RG --name $VNET --location $LOC --address-prefixes $VNET_CIDR

az network vnet subnet create --resource-group $RG --vnet-name $VNET --name $SNET_DB \
  --address-prefixes $SNET_DB_CIDR --delegations Microsoft.DBforPostgreSQL/flexibleServers

az network vnet subnet create --resource-group $RG --vnet-name $VNET --name $SNET_APP \
  --address-prefixes $SNET_APP_CIDR --delegations Microsoft.Web/serverFarms

az network vnet subnet create --resource-group $RG --vnet-name $VNET --name $SNET_PE \
  --address-prefixes $SNET_PE_CIDR
```

Die Delegierung reserviert das Subnetz für den jeweiligen Dienst. Ein delegiertes Subnetz kann nichts anderes aufnehmen.

## Schritt P3 – Private DNS-Zonen

Innerhalb des Netzes lösen die privaten Zonen die Namen auf die privaten Adressen auf. Alle drei Zonen werden mit dem Netz verknüpft:

```bash
for ZONE in $ZONE_PG $ZONE_BLOB $ZONE_APP; do
  az network private-dns zone create --resource-group $RG --name $ZONE
  az network private-dns link vnet create --resource-group $RG --zone-name $ZONE \
    --name "link-$VNET" --virtual-network $VNET --registration-enabled false
done
```

## Schritt P4 – PostgreSQL mit privatem Zugang

```bash
SUBNET_DB_ID=$(az network vnet subnet show --resource-group $RG --vnet-name $VNET --name $SNET_DB --query id --output tsv)
ZONE_PG_ID=$(az network private-dns zone show --resource-group $RG --name $ZONE_PG --query id --output tsv)

az postgres flexible-server create \
  --resource-group $RG --name $PG --location $LOC \
  --version 16 --tier Burstable --sku-name Standard_B1ms --storage-size 32 \
  --backup-retention 35 --geo-redundant-backup Disabled \
  --admin-user $PGADMIN --admin-password $PGPASS \
  --subnet $SUBNET_DB_ID --private-dns-zone $ZONE_PG_ID --yes

az postgres flexible-server db create --resource-group $RG --server-name $PG --name $DBNAME
```

Die Befehle laufen über die Verwaltungsschnittstelle, sie funktionieren also auch ohne Zugang zum Netz. Den **tatsächlichen Servernamen** liest Du aus (nicht raten):

```bash
PG_HOST=$(az postgres flexible-server show --resource-group $RG --name $PG --query fullyQualifiedDomainName --output tsv)
echo "$PG_HOST"
DATABASE_URL="postgresql+psycopg://$PGADMIN:$PGPASS@$PG_HOST:5432/$DBNAME?sslmode=require"
```

`$PG_HOST` muss auf `…postgres.database.azure.com` enden und in der privaten Zone liegen. Die Entscheidung für Sicherungen und Geo-Redundanz aus Schritt 5 der Hauptanleitung gilt unverändert.

## Schritt P5 – Blob Storage nur über Private Endpoint

```bash
SUBNET_PE_ID=$(az network vnet subnet show --resource-group $RG --vnet-name $VNET --name $SNET_PE --query id --output tsv)
SA_ID=$(az storage account show --resource-group $RG --name $SA --query id --output tsv)

az network private-endpoint create --resource-group $RG --name pe-blob --vnet-name $VNET --subnet $SNET_PE \
  --private-connection-resource-id $SA_ID --group-id blob --connection-name pe-blob-conn

az network private-endpoint dns-zone-group create --resource-group $RG --endpoint-name pe-blob \
  --name default --private-dns-zone $ZONE_BLOB --zone-name blob
```

Erst **danach** schaltest Du den öffentlichen Zugang ab. Vorher muss der Container `documents` existieren (Schritt 6 der Hauptanleitung). Danach kommt Dein
Rechner nicht mehr an das Speicherkonto:

```bash
az storage account update --resource-group $RG --name $SA --public-network-access Disabled
```

## Schritt P6 – Web-App ausgehend ins Netz hängen, Einstellungen setzen

```bash
az webapp vnet-integration add --resource-group $RG --name $APP --vnet $VNET --subnet $SNET_APP
```

Die App-Einstellungen entsprechen Schritt 7c der Hauptanleitung, nur mit der `DATABASE_URL` aus Schritt P4. Prüfe zuerst, dass alle Variablen gefüllt sind
(eine leere Variable würde als leere Einstellung gespeichert und die App am Start hindern):

```bash
for v in DATABASE_URL SECRET_KEY ADMIN_PASSWORD PGPASS SA APP RG PG_HOST; do [ -z "${!v}" ] && echo "FEHLT: $v"; done; echo "Prüfung beendet"
```

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

az webapp restart --resource-group $RG --name $APP
```

Verbindungen zu privaten Adressen (10.x.x.x) laufen automatisch durch das Netz. Die Web-App ist an dieser Stelle **noch öffentlich erreichbar**, damit Du
Datenbank und Dokumente zuerst testen kannst:

```bash
curl https://$APP.azurewebsites.net/api/health
```

Erwartet: `{"status":"ok"}`. Melde Dich im Browser an, lege einen Kunden und ein Onboarding an und klicke **„PDF ablegen“**. Funktioniert das, laufen
Datenbank (privat) und Blob Storage (privat) über das Netz.

## Schritt P7 – Eingang der Web-App über Private Endpoint

```bash
APP_ID=$(az webapp show --resource-group $RG --name $APP --query id --output tsv)

az network private-endpoint create --resource-group $RG --name pe-app --vnet-name $VNET --subnet $SNET_PE \
  --private-connection-resource-id $APP_ID --group-id sites --connection-name pe-app-conn

az network private-endpoint dns-zone-group create --resource-group $RG --endpoint-name pe-app \
  --name default --private-dns-zone $ZONE_APP --zone-name sites
```

Der Private Endpoint gilt auch für die Verwaltungsadresse der App (`$APP.scm.azurewebsites.net`, Logs und Terminal).

## Schritt P8 – Privaten Zugang testen, bevor der öffentliche abgeschaltet wird

Du brauchst einen Rechner **im** virtuellen Netz. Am einfachsten ist eine kleine, kurzlebige Linux-VM ohne öffentliche Adresse in einer eigenen Ressourcengruppe.
Du steuerst sie über die Verwaltungsschnittstelle, ohne SSH:

```bash
RG_TEST=rg-servicecheck-test
az group create --name $RG_TEST --location $LOC

az vm create --resource-group $RG_TEST --name vm-nettest \
  --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest --size Standard_B1s \
  --subnet $SUBNET_PE_ID --public-ip-address "" --nsg-rule NONE \
  --admin-username azureuser --generate-ssh-keys

az vm run-command invoke --resource-group $RG_TEST --name vm-nettest --command-id RunShellScript \
  --scripts "getent hosts $APP.azurewebsites.net; curl -s https://$APP.azurewebsites.net/api/health"
```

Erwartet: Der Name löst auf eine Adresse im Bereich **10.20.3.x** auf, und die Antwort ist `{"status":"ok"}`. Steht dort eine öffentliche Adresse, ist die
DNS-Zone nicht (richtig) mit dem Netz verknüpft (Schritt P3 und P7 prüfen). Ist die gewünschte Größe in Eurer Region nicht verfügbar, wähle eine andere.

## Schritt P9 – Öffentlichen Zugang der Web-App abschalten

**Nur wenn Schritt P8 ein richtiges Ergebnis geliefert hat.** Ab jetzt kommt von außen niemand mehr an die App, auch Du nicht:

```bash
az webapp update --resource-group $RG --name $APP --set publicNetworkAccess=Disabled
```

Prüfen: Aus dem Internet (Dein Rechner ohne Netzanbindung) sollte `curl https://$APP.azurewebsites.net/api/health` jetzt eine Fehlermeldung (HTTP 403) liefern,
aus der Test-VM aber weiterhin `{"status":"ok"}`:

```bash
az vm run-command invoke --resource-group $RG_TEST --name vm-nettest --command-id RunShellScript \
  --scripts "curl -s https://$APP.azurewebsites.net/api/health"
```

Wenn Du nach diesem Schritt nicht mehr an die App kommst, ist das Absicht. Mit `--set publicNetworkAccess=Enabled` machst Du den Schritt rückgängig.

## Schritt P10 – Zugang für Eure Benutzer (mit der IT)

Das Azure-Ende ist fertig. Damit Eure Mitarbeiter die App öffnen können, muss die IT zwei Dinge einrichten. Die Befehle hängen von Eurer Umgebung ab:

1. **Netzwerkverbindung** zwischen Firmennetz und dem virtuellen Netz `10.20.0.0/16`: Site-to-Site-VPN, ExpressRoute, Peering zu einem vorhandenen
   Hub-Netz oder ein VPN pro Benutzer (Point-to-Site) in dieses Netz.
2. **Namensauflösung:** Der Name `$APP.azurewebsites.net` muss bei Euren Arbeitsplätzen auf die **private** Adresse zeigen. Üblich ist eine bedingte
   Weiterleitung (Conditional Forwarder) im Firmen-DNS für `azurewebsites.net` an einen DNS-Resolver im virtuellen Netz (z. B. Azure DNS Private Resolver),
   der die private Zone aus Schritt P3 kennt. Eine Alternative ist ein interner Eintrag mit eigenem Namen (z. B. `servicecheck.firma.de`) auf die private IP. Dafür
   braucht die App ein Zertifikat für diesen Namen. Die von Azure verwalteten kostenlosen Zertifikate sind für nicht öffentlich erreichbare Apps in der Regel nicht
   nutzbar. Prüft das mit der IT.

Die Anmeldung über Entra ID bleibt unverändert: Die Umleitung läuft im Browser des Benutzers, er muss dazu nur die App-Adresse erreichen können. Die Umleitungs-URI
`https://$APP.azurewebsites.net/api/auth/oidc/callback` bleibt gleich. Die App selbst muss ausgehend `login.microsoftonline.com` erreichen. Das ist ohne eigene
Netzwerksperren automatisch so.

Danach geht es mit **Schritt 9 (Entra ID)** und **10 (lokale Anmeldung abschalten)** der Hauptanleitung weiter.

## Schritt P11 – Betrieb im privaten Netz

| Aufgabe | Wie |
|---|---|
| Image bauen und App aktualisieren | unverändert: `az acr build` und `az webapp config container set` laufen über öffentliche Adressen bzw. die Verwaltungsschnittstelle |
| Logs ansehen | `az webapp log tail` und das Portal-Logstream benötigen die Verwaltungsadresse der App und funktionieren **nur noch aus dem Netz**. Empfohlen: App-Logs an einen Log-Analytics-Arbeitsbereich senden (Diagnoseeinstellungen), den Du im Portal einsehen kannst |
| Datenbank-Sicherung (`scripts/backup.sh`) und `psql` | nur von einem Rechner im Netz (z. B. kleine VM im Netz oder Bastion). Von Deinem Laptop ohne Anbindung nicht möglich. Die automatische Azure-Sicherung läuft unabhängig davon |
| Wiederherstellung auf einen Zeitpunkt | mit privatem Ziel: `az postgres flexible-server restore --resource-group $RG --name $PG-restore --source-server $PG --restore-time "<ZEITPUNKT>Z" --subnet $SUBNET_DB_ID --private-dns-zone $ZONE_PG_ID`. Danach `DATABASE_URL` mit dem neuen Servernamen setzen (`fullyQualifiedDomainName` auslesen) |
| Dokumente zurückholen (Soft Delete) | aus dem Netz, oder im Portal; der öffentliche Zugang des Speicherkontos ist aus |

## Aufräumen der Test-VM

```bash
az group delete --name $RG_TEST --yes --no-wait
```

Die Test-VM kostet laufend Geld. Lösche sie, sobald der Test abgeschlossen ist. Private Endpoints und private DNS-Zonen verursachen ebenfalls kleine laufende Kosten.

## Fehlersuche

| Symptom | Mögliche Ursache und Abhilfe |
|---|---|
| App-Log: `could not translate host name` oder `Name or service not known` (Datenbank) | Private DNS-Zone der Datenbank nicht mit dem Netz verknüpft (Schritt P3), App nicht in das Netz integriert (Schritt P6), oder `$PG_HOST` falsch (aus `fullyQualifiedDomainName` übernehmen) |
| App-Log: Timeout zur Datenbank | VNet-Integration fehlt oder zeigt auf das falsche Subnetz, Datenbank-Subnetz nicht an PostgreSQL delegiert (Schritt P2), oder eine Netzwerksicherheitsgruppe blockiert Port 5432 |
| `az webapp vnet-integration add` schlägt fehl | Subnetz nicht an `Microsoft.Web/serverFarms` delegiert oder bereits von einem anderen App-Service-Plan belegt. Netz und Plan müssen in derselben Region liegen |
| Dokumente ablegen/abrufen liefert 503 („Dokumentenspeicher“) | Private Endpoint oder DNS-Zone des Blob-Speichers fehlt (Schritt P5, `getent hosts $SA.blob.core.windows.net` aus dem Netz muss eine 10.20.3.x liefern). Rollenzuweisung der Managed Identity unverändert prüfen |
| Browser: „403 – Web App – Unavailable“ oder keine Seite | Der Name zeigt noch auf die öffentliche Adresse (DNS im Firmennetz, Schritt P10), oder die Verbindung ins Netz fehlt |
| `az webapp log tail` hängt oder liefert nichts | Verwaltungsadresse nur im Netz erreichbar, siehe Schritt P11 |
| `az postgres flexible-server create` meldet eine fehlerhafte DNS-Zone | Der Zonenname muss auf `.private.postgres.database.azure.com` enden und im selben Abonnement/Ressourcengruppe liegen (oder die volle Ressourcen-ID verwenden) |

## Aufräumen (alles löschen)

```bash
az group delete --name $RG --yes --no-wait
az group delete --name $RG_TEST --yes --no-wait
```
