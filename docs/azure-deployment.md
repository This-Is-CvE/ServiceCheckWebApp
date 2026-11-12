# Service Check in Azure bereitstellen – mit privatem Netzwerk (Mac)

Diese Anleitung ist die **einzige** für die Bereitstellung in Azure. Sie geht davon aus, dass **alles privat ist**: Datenbank, Dokumentenspeicher **und die Web-App** haben
keinen öffentlichen Zugang, sondern nur private Endpoints in einem virtuellen Netz. Alle Befehle laufen im Terminal eines **Macs**.

```
Firmennetz ──(VPN/Peering, Eure IT)──► virtuelles Netz  10.163.13.0/24
                                        ├─ snet-db   10.163.13.0/27    PostgreSQL (private IP)
                                        ├─ snet-app  10.163.13.32/27   VNet-Integration der Web-App (ausgehend)
                                        ├─ snet-pe   10.163.13.64/27   Private Endpoints: Web-App (Eingang), Blob Storage
                                        └─ frei      10.163.13.96 – .255  Reserve (z. B. VPN-Gateway, weitere Dienste)
Öffentlich bleiben nur: Container Registry (Images ohne Personendaten) und die Azure-Verwaltung (az, Portal).
```

| Baustein | Azure-Dienst | Zugang |
|---|---|---|
| Anwendung (Container) | App Service für Linux | Eingang nur über **Private Endpoint**, ausgehend über **VNet-Integration** |
| Container-Image | Container Registry (das Image wird **in Azure** gebaut, Docker auf Deinem Mac ist nicht nötig) | öffentlich (ein privater Zugang braucht die Premium-Stufe) |
| Datenbank | PostgreSQL Flexible Server | **private IP**, kein öffentlicher Zugang |
| Dokumente (PDFs) | Blob Storage | nur **Private Endpoint** |
| Anmeldung | Microsoft Entra ID | Browser des Benutzers zu Microsoft |

> **Was geprüft ist und was nicht:** Die Anwendung (Migrationen, Entra-Anmeldung, Blob-Ablage, Backup-Skripte) ist mit automatisierten Tests geprüft, auch gegen ein echtes PostgreSQL 16.
> Jeden `az`-Befehl dieser Anleitung habe ich gegen die Azure-CLI abgeglichen (Befehle und Parameter existieren), und die Befehlsblöcke habe ich in bash und zsh auf Syntax geprüft.
> **Gegen ein Azure-Abonnement oder auf einem echten Mac habe ich sie nicht ausgeführt.** Am anfälligsten sind **Kontingente**, **Rechte auf dem Netz**, **Namensauflösung (DNS)** und die
> **Anbindung Eures Firmennetzes**. Dafür gibt es Prüfschritte und eine Fehlersuche am Ende.
>
> **Kosten:** Alle Ressourcen verursachen laufende Kosten (Plan, Datenbank, Private Endpoints, DNS-Zonen, kurzzeitig die Test-VM). Prüft die Preise im Azure-Preisrechner. Wenn Ihr nur testet,
> löscht alles am Ende wieder (Anhang C).

## Die Schritte im Überblick

| # | Schritt | Wer |
|---|---|---|
| 1 | Voraussetzungen und was vorab zu klären ist | Du + IT |
| 2 | Mac einrichten (Homebrew, Azure-CLI, zsh, Anmeldung) | Du |
| 3 | Variablen festlegen | Du |
| 4 | Vorab prüfen (Abonnement, Region, Namen, Dienste) | Du |
| 5 | Ressourcengruppe | Du |
| 6 | Netz prüfen und IDs auflösen | Du (Netz: IT) |
| 7 | Container Registry und Image | Du |
| 8 | Speicherkonto | Du |
| 9 | Private DNS-Zonen | Du |
| 10 | PostgreSQL privat | Du |
| 11 | Blob Storage privat schalten | Du |
| 12 | App-Service-Plan, Web-App, Rechte | Du |
| 13 | Web-App ans Netz hängen, Einstellungen, Test | Du |
| 14 | Private Endpoint der Web-App | Du |
| 15 | Privaten Zugang testen | Du |
| 16 | Öffentlichen Zugang der Web-App abschalten | Du |
| 17 | Zugang für Eure Benutzer (Netz, DNS, eigener Name mit Zertifikat) | IT + Du |
| 18 | Anmeldung mit Entra ID | Du + IT |
| 19 | Lokale Anmeldung abschalten | Du |
| 20 | Datensicherung und Wiederherstellung | Du |
| 21 | Updates einspielen | Du |
| A–E | Anhang: Ports, Fehlersuche, Aufräumen, nächste Schritte, Werte nach neuem Terminal | |

---

## Schritt 1 – Voraussetzungen und was vorab zu klären ist

### Auf dem Mac

| Was | Wofür | Prüfen | Installieren |
|---|---|---|---|
| **macOS**, aktuelle Version (Intel oder Apple Silicon) | Grundlage | `sw_vers` | Systemeinstellungen, Softwareupdate. Bei sehr altem macOS kann die Installation von Homebrew und Azure-CLI scheitern |
| **Administratorrechte** auf dem Mac | Installation von Homebrew | `sudo -v` fragt nach Deinem Passwort | bei einem Firmen-Mac über die IT, siehe „Firmen-Mac“ in Schritt 2 |
| **Homebrew** | Paketverwaltung, installiert die Azure-CLI | `brew --version` | Schritt 2 |
| **Azure-CLI (`az`)** | alle Azure-Befehle | `az version` | `brew install azure-cli` |
| **`openssl`** | Zufallswerte für Passwörter und Schlüssel | `openssl rand -hex 4` | **im Mac enthalten** (LibreSSL) |
| **`curl`**, **`nslookup`** | App-Test, Namensprüfung | `curl --version` | **im Mac enthalten** |
| **`git`** | Quellcode holen, **nur wenn Du das Image neu bauen musst** (Schritt 7, 21) | `git --version` | beim ersten Aufruf bietet macOS die „Command Line Tools“ an, oder `brew install git` |
| **Texteditor** (`nano`) und **Webbrowser** | `azure.env` bearbeiten, `az login`, Portal, Entra | – | im Mac enthalten |

**Nicht nötig:** Docker Desktop, Python, Node.js. Python und Node.js brauchst Du nur, wenn Du die App **lokal** auf dem Mac starten willst (siehe README).

### In Azure und bei der IT (vorab klären)

- **Abonnement und Rollen:**
  - Auf der Ressourcengruppe der Anwendung (`$RG`): *Mitwirkender* **plus** *Benutzerzugriffsadministrator* (oder *Besitzer*). Letzteres ist für die Rollenzuweisungen der Managed Identity in Schritt 12 nötig.
  - Auf der Ressourcengruppe des **virtuellen Netzes** (`$RG_NET`): *Netzwerkmitwirkender* (oder mindestens das Recht `Microsoft.Network/virtualNetworks/subnets/join/action`). Ohne dieses Recht scheitern Datenbank,
    Private Endpoints und VNet-Integration.
  - Für Schritt 18 (Entra-App-Registrierung): Rechte im Entra-Admin-Center (z. B. *Anwendungsentwickler* oder *Cloudanwendungsadministrator*), oder die IT erledigt es.
- **Das virtuelle Netz:** Name, **Ressourcengruppe**, Region, die drei Subnetze und ihre **Delegierungen** (`snet-db` an `Microsoft.DBforPostgreSQL/flexibleServers`, `snet-app` an `Microsoft.Web/serverFarms`, `snet-pe` ohne). Der Adressbereich darf
  sich nicht mit dem Firmennetz überschneiden (Vorschlag in Schritt 6).
- **Kontingent für App Service:** In neuen oder für andere Zwecke angelegten Abonnements ist das Kontingent für den App-Service-Plan in der Region oft **0** (siehe Schritt 12). Das kann ein Antrag nötig machen.
- **Richtlinien (Azure Policy):** Frag die IT, ob auf Abonnement oder Ressourcengruppe Richtlinien liegen, die SKUs, Regionen, Tags oder öffentlichen Zugang vorgeben.
- **Anbindung des Firmennetzes und DNS** (Schritt 17): Wie kommen die Arbeitsplätze zum virtuellen Netz, und wie lösen sie den App-Namen auf? **Das ist die größte Abhängigkeit.** Ohne diese Anbindung kann niemand die App aufrufen,
  nachdem der öffentliche Zugang abgeschaltet ist.
- **Region:** Netz, App-Service-Plan, Datenbank, Speicherkonto und Private Endpoints liegen in **derselben Region** (`$LOC`).
- **Netzwerkzugriff** vom Mac (ausgehend, HTTPS/443): `login.microsoftonline.com`, `management.azure.com`, Eure Registry `*.azurecr.io`, `github.com`. Für die Installation zusätzlich `raw.githubusercontent.com` (Homebrew).
- **Nur für ein neues Image:** ein GitHub-Zugriffstoken mit Leserecht auf das private Repository (Fine-grained Token, nur dieses Repository, „Contents: read“).

## Schritt 2 – Mac einrichten

**2.1 Homebrew** (einmalig). Das Programm installiert bei Bedarf zuerst die „Command Line Tools“ von Apple und fragt nach Deinem Passwort:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Am Ende zeigt der Installer unter „Next steps“ zwei Zeilen, die Homebrew in den Suchpfad eintragen. **Führe diese Zeilen aus**, sonst findet das Terminal `brew` nicht. Bei Apple Silicon:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Bei einem Intel-Mac liegt Homebrew unter `/usr/local`, dann steht der passende Pfad in der Ausgabe des Installers.

**2.2 Azure-CLI:**

```bash
brew update
brew install azure-cli
```

Die Befehle dieser Anleitung sind gegen die Azure-CLI 2.91 abgeglichen, eine neuere Version ist unproblematisch (`brew upgrade azure-cli`). Neuere Versionen zeigen bei jedem Aufruf manchmal eine **`SyntaxWarning: "\/" is an invalid escape sequence`**.
Das ist ein harmloser Schönheitsfehler im Programmcode der CLI und keine Fehlermeldung. Mit `export PYTHONWARNINGS=ignore` blendest Du sie in diesem Terminalfenster aus.

**2.3 Die zsh richtig einstellen (wichtig).** Das Terminal des Macs benutzt **zsh**. Dort gelten Kommentare mit `#` beim **Einfügen** nicht als Kommentar. Aus `RG='meine-gruppe'   # Name der Gruppe` wird ein anderer Befehl, und **die Variable
wird nicht gesetzt**, ohne klare Fehlermeldung. Behebe das einmalig und dauerhaft:

```bash
echo 'setopt interactive_comments' >> ~/.zshrc
source ~/.zshrc
```

Für ein bereits offenes Fenster reicht `setopt interactive_comments`. Alternativ startest Du mit `bash` eine Bash-Sitzung (macOS zeigt dazu einen Hinweis zur zsh, den Du ignorieren kannst). Die Prüfschleifen in dieser Anleitung laufen in zsh und bash.

**2.4 Prüfen, ob der Mac bereit ist:**

```bash
for t in brew az openssl curl nslookup git; do
  if command -v $t >/dev/null 2>&1; then echo "OK      $t"; else echo "FEHLT   $t"; fi
done
echo "Shell: $SHELL"
openssl rand -hex 4 >/dev/null 2>&1 && echo "OK      openssl rand" || echo "FEHLT   openssl rand"
az version --query '"azure-cli"' --output tsv 2>/dev/null
```

Erwartet: `OK` für `brew`, `az`, `openssl`, `curl`, `nslookup` (`git` nur für ein neues Image), `Shell: /bin/zsh` und eine Versionsnummer der Azure-CLI. Fällt `openssl rand` aus, nimm statt `openssl rand -hex 16` diese Alternative:
`LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 32`.

**2.5 Anmelden und Abonnement wählen:**

```bash
az login
az account list --output table
az account set --subscription "Name oder ID Deines Abonnements"
az account show --query "{Abo:name, id:id, Mandant:tenantId}" --output table
```

`az login` öffnet den Browser. Geht das nicht (z. B. gesperrter Browser), nimm `az login --use-device-code` und gib den angezeigten Code auf https://microsoft.com/devicelogin ein. Notiere Dir die **Mandanten-ID** (`tenantId`, für Schritt 18).
Prüfe, dass das **Abonnement** das ist, in dem das Netz liegt. Das Portal und die CLI können unterschiedliche Abonnements zeigen.

**Firmen-Mac:**
- **Homebrew blockiert oder keine Administratorrechte:** Nutze die **Azure Cloud Shell** (Bash im Browser, https://shell.azure.com). Dort sind `az`, `openssl`, `curl` und `git` vorhanden, und Du bist angemeldet. Diese Anleitung läuft dort unverändert. Variablen gehen nach etwa
  20 Minuten Inaktivität verloren, nutze die Datei `~/azure.env` aus Schritt 3.
- **Proxy oder TLS-Prüfung** (Zertifikatsfehler bei `az`): Nach Microsofts Dokumentation setzt Du den Pfad zum Firmenzertifikat, z. B. `export REQUESTS_CA_BUNDLE=/pfad/zum/firmenzertifikat.pem`. Schalte die Zertifikatsprüfung **nicht** ab.
- Von Deinem Mac erreichst Du die private Web-App und die private Datenbank nur über die Netzanbindung der Firma. Die Anleitung testet deshalb mit einer Test-VM und der Azure-Verwaltung (Schritt 15).

## Schritt 3 – Variablen festlegen

Alle Befehle benutzen Variablen. **Pro Terminalfenster gehen sie verloren**, deshalb legst Du sie **einmal** in der Datei `~/azure.env` ab (in Deinem Benutzerordner, **nicht** im Projekt, nicht in Git) und lädst sie in jedem Terminal mit `source ~/azure.env`:

```bash
nano ~/azure.env       # Vorlage unten einfügen, Werte eintragen; speichern mit Control+O und Enter, beenden mit Control+X
chmod 600 ~/azure.env  # nur Du darfst die Datei lesen
source ~/azure.env
```

**Vorlage** (Ressourcen, die es schon gibt, mit dem echten Namen eintragen; neue Ressourcen: Namen selbst festlegen). Ersetze jedes `HIER-EINTRAGEN`:

```bash
# --- Anwendung ---
RG='HIER-EINTRAGEN'                 # Ressourcengruppe der Anwendung (az group list --output table)
LOC='HIER-EINTRAGEN'                # Region, z. B. germanywestcentral; MUSS die Region des Netzes sein
SUFFIX='HIER-EINTRAGEN'             # kurz, nur Kleinbuchstaben/Ziffern, z. B. pco2; macht weltweite Namen eindeutig
ACR="acrservicecheck${SUFFIX}"      # nur Kleinbuchstaben und Ziffern
PG="pg-servicecheck-${SUFFIX}"      # Datenbankserver
SA="stservicecheck${SUFFIX}"        # Speicherkonto: 3-24 Zeichen, nur Kleinbuchstaben und Ziffern
PLAN='plan-servicecheck'
PLAN_SKU='P0V3'                     # Stufe des App-Service-Plans; bei Kontingentfehler S1 oder B1 versuchen (Schritt 12)
APP="app-servicecheck-${SUFFIX}"    # Adresse: https://$APP.azurewebsites.net (weltweit eindeutig)
DBNAME='servicecheck'
PGADMIN='scadmin'

# --- Netz (liegt oft in einer anderen Ressourcengruppe, von der IT angelegt) ---
RG_NET='HIER-EINTRAGEN'             # Ressourcengruppe des virtuellen Netzes (az network vnet list --output table)
VNET='HIER-EINTRAGEN'               # Name des virtuellen Netzes
SNET_DB='snet-db'
SNET_APP='snet-app'
SNET_PE='snet-pe'
ZONE_PG='servicecheck.private.postgres.database.azure.com'   # muss auf .private.postgres.database.azure.com enden
ZONE_BLOB='privatelink.blob.core.windows.net'
ZONE_APP='privatelink.azurewebsites.net'
VM_SIZE='Standard_B2ts_v2'          # Test-VM (Schritt 15); die alte B-Serie Bv1 (Standard_B1s) ist End of Life

# --- Geheimnisse: EINMAL erzeugen, hier eintragen und im Passwort-Manager ablegen ---
# Erzeugen mit:  openssl rand -hex 16   (PGPASS)   und   openssl rand -hex 32   (SECRET_KEY)
PGPASS='HIER-EINTRAGEN'
SECRET_KEY='HIER-EINTRAGEN'
ADMIN_PASSWORD='HIER-EINTRAGEN'     # mindestens 10 Zeichen, nicht "admin"

# --- Prüfung beim Laden: nennt jede Variable, die leer ist oder noch den Platzhalter enthält ---
for v in RG LOC SUFFIX ACR PG SA PLAN PLAN_SKU APP DBNAME PGADMIN RG_NET VNET SNET_DB SNET_APP SNET_PE VM_SIZE PGPASS SECRET_KEY ADMIN_PASSWORD; do
  eval "val=\${$v}"
  if [ -z "$val" ] || [ "$val" = "HIER-EINTRAGEN" ]; then echo "FEHLT: $v"; fi
done
echo "Prüfung beendet"
```

Steht beim Laden **kein** `FEHLT:` vor „Prüfung beendet“, bist Du fertig.

- **Die Geheimnisse erzeugst Du nur einmal.** `PGPASS` muss dem Passwort entsprechen, mit dem der Datenbankserver angelegt wird. Würdest Du es bei jedem Terminal neu würfeln, passt es nicht mehr zum Server. Hast Du es doch verloren, setzt Du das Datenbankpasswort nach Schritt 10 zurück:
  `az postgres flexible-server update --resource-group $RG --name $PG --admin-password "$PGPASS"`. Ein neuer `SECRET_KEY` meldet nur alle angemeldeten Nutzer ab.
- Schreibe `PGPASS`, `SECRET_KEY` und `ADMIN_PASSWORD` zusätzlich in Euren Passwort-Manager.
- **Namen:** Web-App, Registry, Speicherkonto und Datenbankserver heißen **weltweit eindeutig**. Wenn es frühere Versuche mit denselben Namen gab (auch in einem anderen Abonnement), sind sie belegt. Wähle dann ein neues `SUFFIX` (Prüfung in Schritt 4).

## Schritt 4 – Vorab prüfen

Fünf Minuten, die viel Ärger sparen. Du prüfst, ob die CLI im richtigen Abonnement und in der richtigen Region arbeitet, ob die Namen frei sind und ob die Azure-Dienste registriert sind.

```bash
# 1) Richtiges Abonnement? Vergleiche die ID mit dem Portal (Abonnements, Übersicht)
az account show --query "{name:name, id:id}" --output table

# 2) Gleiche Region überall? Alle Zeilen müssen dieselbe Region zeigen
echo "LOC=$LOC"
az network vnet show --resource-group $RG_NET --name $VNET --query location --output tsv

# 3) Sind die weltweit eindeutigen Namen frei? (true = frei)
az acr check-name --name $ACR --query nameAvailable
az storage account check-name --name $SA --query nameAvailable
nslookup $APP.azurewebsites.net
```

Bei `nslookup` heißt `NXDOMAIN` **frei**. Erscheinen IP-Adressen, ist der Name der Web-App vergeben. Bei `false` oder vergebenem Namen änderst Du `SUFFIX` in `~/azure.env` und lädst neu. Der Datenbankname lässt sich vorab nicht prüfen. Ist er belegt, meldet es Schritt 10.

```bash
# 4) Dienste registriert? Jeder muss "Registered" zeigen; sonst mit dem Befehl darunter registrieren
for ns in Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL Microsoft.Network Microsoft.Storage Microsoft.Web; do
  printf "%-32s" $ns; az provider show --namespace $ns --query registrationState --output tsv
done
```

Steht bei einem Dienst `NotRegistered`:

```bash
az provider register --namespace Microsoft.Web --wait
```

(ersetze `Microsoft.Web` durch den betroffenen Dienst).

## Schritt 5 – Ressourcengruppe anlegen

Nur, wenn es `$RG` noch nicht gibt (`az group exists --name $RG` zeigt `true` oder `false`):

```bash
az group create --name $RG --location $LOC
```

## Schritt 6 – Netz prüfen und IDs auflösen

Das virtuelle Netz liegt meist in **einer anderen Ressourcengruppe** (`$RG_NET`) als die Anwendung (`$RG`) und wurde von der IT mit Subnetzen und Delegierungen angelegt. Weil Azure einen bloßen Netznamen nur in der **eigenen** Ressourcengruppe sucht, arbeiten alle folgenden Schritte
mit den **Ressourcen-IDs** von Netz und Subnetzen. Du löst sie **einmal** auf (und wieder, wenn Du ein neues Terminal öffnest, siehe Anhang E):

```bash
VNET_ID=$(az network vnet show --resource-group $RG_NET --name $VNET --query id --output tsv)
SUBNET_DB_ID=$(az network vnet subnet show --resource-group $RG_NET --vnet-name $VNET --name $SNET_DB --query id --output tsv)
SUBNET_APP_ID=$(az network vnet subnet show --resource-group $RG_NET --vnet-name $VNET --name $SNET_APP --query id --output tsv)
SUBNET_PE_ID=$(az network vnet subnet show --resource-group $RG_NET --vnet-name $VNET --name $SNET_PE --query id --output tsv)
for v in VNET_ID SUBNET_DB_ID SUBNET_APP_ID SUBNET_PE_ID; do eval "val=\${$v}"; [ -z "$val" ] && echo "FEHLT: $v"; done; echo "Prüfung beendet"
```

Kommt `FEHLT:` oder eine Fehlermeldung, stimmen `RG_NET`, `VNET` oder die Subnetz-Namen nicht, oder Dir fehlt das Leserecht auf dem Netz. Dann prüfe das Netz (lesend, es ändert nichts):

```bash
az network vnet show --resource-group $RG_NET --name $VNET \
  --query "{name:name, region:location, bereich:addressSpace.addressPrefixes[0]}" --output table

az network vnet subnet list --resource-group $RG_NET --vnet-name $VNET \
  --query "[].{name:name, bereich:addressPrefix, delegation:delegations[0].serviceName}" --output table
```

Erwartet: Region wie `$LOC`, `snet-db` mit Delegierung **`Microsoft.DBforPostgreSQL/flexibleServers`**, `snet-app` mit **`Microsoft.Web/serverFarms`**, `snet-pe` **ohne** Delegierung. Fehlt eine Delegierung und hast Du das Recht dazu, hole sie nach:

```bash
az network vnet subnet update --resource-group $RG_NET --vnet-name $VNET --name $SNET_DB  --delegations Microsoft.DBforPostgreSQL/flexibleServers
az network vnet subnet update --resource-group $RG_NET --vnet-name $VNET --name $SNET_APP --delegations Microsoft.Web/serverFarms
```

**Adressbereich (Vorschlag, mit der IT abstimmen):** `10.163.13.0/24` (256 Adressen), aufgeteilt in drei Subnetze mit je `/27` (32 Adressen, davon 27 nutzbar, Azure reserviert je 5):

| Subnetz | Bereich | Nutzbare Adressen |
|---|---|---|
| `snet-db` | `10.163.13.0/27` | `.4` bis `.30` |
| `snet-app` | `10.163.13.32/27` | `.36` bis `.62` |
| `snet-pe` | `10.163.13.64/27` | `.68` bis `.94` |
| frei | `10.163.13.96/27` bis `.255` | Reserve, z. B. ein `GatewaySubnet` (`/27`) für ein VPN-Gateway |

Mindestgröße für Datenbank- und App-Subnetz ist `/28`. `/27` lässt Platz zum Wachsen (weitere App-Instanzen, eine Wiederherstellung neben dem laufenden Server). Ist der zugeteilte Bereich kleiner als `/24`: Mit einem `/26` geht es gerade noch mit drei `/28`, ohne Platz für ein VPN-Gateway.

Legst Du das Netz **selbst** an (statt es von der IT zu bekommen):

```bash
VNET_CIDR=10.163.13.0/24
az network vnet create --resource-group $RG_NET --name $VNET --location $LOC --address-prefixes $VNET_CIDR

az network vnet subnet create --resource-group $RG_NET --vnet-name $VNET --name $SNET_DB \
  --address-prefixes 10.163.13.0/27 --delegations Microsoft.DBforPostgreSQL/flexibleServers

az network vnet subnet create --resource-group $RG_NET --vnet-name $VNET --name $SNET_APP \
  --address-prefixes 10.163.13.32/27 --delegations Microsoft.Web/serverFarms

az network vnet subnet create --resource-group $RG_NET --vnet-name $VNET --name $SNET_PE \
  --address-prefixes 10.163.13.64/27
```

Die Delegierung reserviert das Subnetz für den jeweiligen Dienst. Ein delegiertes Subnetz kann nichts anderes aufnehmen.

## Schritt 7 – Container Registry und Image

```bash
az acr create --resource-group $RG --name $ACR --sku Basic
```

Prüfe, ob das Image schon da ist (nur relevant, wenn die Registry bereits existierte):

```bash
az acr repository show-tags --name $ACR --repository servicecheck --output table
```

Steht dort **`1`**, ist alles bereit. Sonst baust Du das Image **in Azure** (Docker auf dem Mac ist nicht nötig, und das Docker-Hub-Problem Eures Netzes spielt keine Rolle). Dafür brauchst Du den **Quellcode**. Das Repository ist privat, `git` fragt nach Benutzername und Kennwort,
als Kennwort gibst Du das **GitHub-Zugriffstoken** ein (nicht Dein GitHub-Passwort). Gib das Token nur auf die Frage von `git` ein, nicht in eine Datei oder Befehlszeile:

```bash
git clone --branch claude/msp-service-check-onboarding-96hqx2 https://github.com/This-Is-CvE/ServiceCheckWebApp.git
cd ServiceCheckWebApp
az acr build --registry $ACR --image servicecheck:1 --file Dockerfile .
```

Der Build dauert einige Minuten und endet mit `Run ID: ... was successful`. Auf manchen Test-Abonnements sind *ACR Tasks* gesperrt. Dann bricht der Befehl mit einem Fehler ab. Alternativ baust Du lokal mit Docker (`docker build -t $ACR.azurecr.io/servicecheck:1 .`),
meldest Dich mit `az acr login --name $ACR` an und lädst mit `docker push` hoch. Das braucht funktionierendes Docker.

## Schritt 8 – Speicherkonto für Dokumente

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

- `Standard_LRS` hält drei Kopien in einem Rechenzentrum. Für mehr Ausfallsicherheit nimm `Standard_ZRS` (Zonen) oder `Standard_GRS` (zweite Region), sofern die Region das anbietet.
- **Versionierung und „Soft Delete“** schützen vor versehentlichem Löschen oder Überschreiben. Gelöschte Dokumente lassen sich 30 Tage lang zurückholen.
- `az storage container create` kann mit „Berechtigung fehlt“ scheitern, wenn Dein Konto keine Datenrolle hat. Dann gib Dir selbst die Rolle *Storage Blob Data Contributor* auf dem Speicherkonto.
- **Den Container legst Du jetzt an**, solange das Speicherkonto noch öffentlich erreichbar ist. In Schritt 11 wird der öffentliche Zugang abgeschaltet.

## Schritt 9 – Private DNS-Zonen

Innerhalb des Netzes lösen private Zonen die Namen auf die privaten Adressen auf. Alle drei Zonen werden mit dem virtuellen Netz verknüpft:

```bash
for ZONE in $ZONE_PG $ZONE_BLOB $ZONE_APP; do
  az network private-dns zone create --resource-group $RG --name $ZONE
  az network private-dns link vnet create --resource-group $RG --zone-name $ZONE \
    --name "link-$VNET" --virtual-network $VNET_ID --registration-enabled false
done
```

Das Verknüpfen braucht das Recht, das Netz zu verwenden (siehe Schritt 1, Rolle *Netzwerkmitwirkender*).

## Schritt 10 – PostgreSQL mit privatem Zugang

```bash
ZONE_PG_ID=$(az network private-dns zone show --resource-group $RG --name $ZONE_PG --query id --output tsv)

az postgres flexible-server create \
  --resource-group $RG --name $PG --location $LOC \
  --version 16 --tier Burstable --sku-name Standard_B1ms --storage-size 32 \
  --backup-retention 35 --geo-redundant-backup Disabled \
  --admin-user $PGADMIN --admin-password $PGPASS \
  --subnet $SUBNET_DB_ID --private-dns-zone $ZONE_PG_ID --yes

az postgres flexible-server db create --resource-group $RG --server-name $PG --name $DBNAME
```

Das dauert einige Minuten. Die Befehle laufen über die Verwaltungsschnittstelle und funktionieren auch ohne Zugang zum Netz.

- `--backup-retention 35`: Azure sichert täglich automatisch und ermöglicht die Wiederherstellung auf einen beliebigen Zeitpunkt der letzten 35 Tage. `--geo-redundant-backup Enabled` legt zusätzlich eine Kopie in einer anderen Region an, lässt sich aber nur **beim Anlegen** festlegen. Entscheide das jetzt.
- Der Netzwerkmodus (privat) wird beim Anlegen gewählt und lässt sich nach meinem Kenntnisstand nachträglich nicht umstellen. Prüfe das in der aktuellen Microsoft-Dokumentation.
- Ist `Standard_B1ms` in Eurer Region nicht verfügbar (Kapazität oder Kontingent, oder die Burstable-Serie ist dort als veraltet gekennzeichnet), wähle ein anderes SKU: `az postgres flexible-server list-skus --location $LOC --output table` zeigt, was verfügbar ist.
- Ist der Servername vergeben, hänge etwas an `SUFFIX` an.

Den **tatsächlichen Servernamen** liest Du aus (nicht raten) und baust die Datenbank-URL für die App:

```bash
PG_HOST=$(az postgres flexible-server show --resource-group $RG --name $PG --query fullyQualifiedDomainName --output tsv)
echo "$PG_HOST"
DATABASE_URL="postgresql+psycopg://$PGADMIN:$PGPASS@$PG_HOST:5432/$DBNAME?sslmode=require"
```

`$PG_HOST` muss auf `…postgres.database.azure.com` enden und in der privaten Zone liegen. SSL ist bei Flexible Server standardmäßig Pflicht.

## Schritt 11 – Blob Storage nur über Private Endpoint

```bash
SA_ID=$(az storage account show --resource-group $RG --name $SA --query id --output tsv)

az network private-endpoint create --resource-group $RG --name pe-blob --subnet $SUBNET_PE_ID \
  --private-connection-resource-id $SA_ID --group-id blob --connection-name pe-blob-conn

az network private-endpoint dns-zone-group create --resource-group $RG --endpoint-name pe-blob \
  --name default --private-dns-zone $ZONE_BLOB --zone-name blob
```

Prüfe, ob der Private Endpoint wirklich angelegt wurde. Fehlt er, schlägt der zweite Befehl mit `ResourceNotFound ... pe-blob` fehl:

```bash
az network private-endpoint list --resource-group $RG --output table
```

Ist `pe-blob` nicht in der Liste, hat der erste Befehl einen Fehler gemeldet (häufig `LinkedAuthorizationFailed`: Dir fehlt auf dem Subnetz in `$RG_NET` das Recht *Netzwerkmitwirkender*). Beseitige die Ursache und wiederhole beide Befehle.

Erst **wenn der Private Endpoint steht**, schaltest Du den öffentlichen Zugang ab. Danach kommt Dein Mac nicht mehr an das Speicherkonto:

```bash
az storage account update --resource-group $RG --name $SA --public-network-access Disabled
```

## Schritt 12 – App-Service-Plan, Web-App und Rechte

**12.1 Plan und Web-App (mit Managed Identity):**

```bash
az appservice plan create --resource-group $RG --name $PLAN --is-linux --sku $PLAN_SKU --location $LOC

az webapp create --resource-group $RG --plan $PLAN --name $APP \
  --container-image-name $ACR.azurecr.io/servicecheck:1 \
  --assign-identity '[system]'

az webapp update --resource-group $RG --name $APP --https-only true
az webapp config set --resource-group $RG --name $APP --always-on true --min-tls-version 1.2 --ftps-state Disabled
```

> **Kontingent (häufigste Stolperstelle):** Meldet `az appservice plan create` `Operation cannot be completed without additional quota` (`Current Limit (B1 VMs): 0`), ist das Kontingent für diese Stufe in Eurem Abonnement und dieser Region **0**. Es ist **kein Rechteproblem** (die Meldung trägt den irreführenden Code
> `Unauthorized`) und meist auch keine Richtlinie.
> - Probiere eine andere Stufe: `PLAN_SKU=S1`, dann `B1` oder `P1V3`. Das Kontingent gilt je Stufe getrennt.
> - Stelle den Antrag im Portal: *Kontingente* (oder *Abonnements → Nutzung + Kontingente*), Anbieter **App Service (Public Preview)**, Region wie `$LOC`, Zeile der gewünschten Stufe, Stift-Symbol *Request adjustment*, neues Limit z. B. **2**. Beachte, dass nach Microsofts Beschreibung **zwei** Limits reichen müssen, das der Stufe **und** das Sammelkontingent
>   *Total Regional VMs* der Region. Das Sammelkontingent steigt beim Anfordern einer Stufe automatisch mit. Schlägt die Selbstbedienung fehl, eröffne eine Supportanfrage (Problemtyp *Service- und Abonnementlimits (Kontingente)*, Typ *App Service*).
> - Auch das Anlegen im Portal zeigt dieselbe Meldung, solange das Kontingent fehlt. Die Anzeige von „0 von 30“ in der Kontingentseite ist nicht das, was beim Anlegen geprüft wird.
> - Die Kontingente der **virtuellen Maschinen** (Anbieter *Compute*) sind davon getrennt. Dort ist die Familie `Standard BS` (Bv1) als *End of Life* gekennzeichnet. Das betrifft VMs, nicht den App-Service-Plan.
> - Die Region **muss** die des Netzes bleiben. Eine andere Region geht nicht.
> - Hinweis: In der Ausgabe kann ein Feld `freeOfferExpirationTime` erscheinen. Das deutet auf einen befristeten Gratis-Zeitraum hin. Prüfe die Kosten in der Kostenverwaltung, bevor er endet.

> **Name der Web-App bereits vergeben:** Meldet `az webapp create` `Webapp '...' already exists ... Unable to retrieve details of the existing app`, ist der Name **weltweit** vergeben (oft durch einen früheren Versuch in einem anderen Abonnement). Es wurde **nichts** angelegt.
> Wähle ein anderes `SUFFIX` (Schritt 4, `nslookup`).

**12.2 Rechte der Managed Identity** (die App braucht keine Passwörter für Registry und Dokumentenspeicher):

```bash
PRINCIPAL=$(az webapp identity show --resource-group $RG --name $APP --query principalId --output tsv)
ACR_ID=$(az acr show --name $ACR --query id --output tsv)
SA_ID=$(az storage account show --resource-group $RG --name $SA --query id --output tsv)

az role assignment create --assignee-object-id $PRINCIPAL --assignee-principal-type ServicePrincipal --role AcrPull --scope $ACR_ID
az role assignment create --assignee-object-id $PRINCIPAL --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" --scope $SA_ID

az webapp config set --resource-group $RG --name $APP --acr-use-identity true --acr-identity '[system]'
```

Rollenzuweisungen brauchen bis zu ein paar Minuten, bis sie wirken. Bis dahin kann die App ihr Image nicht laden (`ImagePullUnauthorizedFailure` im Protokoll). Das erledigt sich mit dem Neustart in Schritt 13.

**Prüfe, dass die Rollen wirklich vergeben sind.** Das ist eine der häufigsten Stolperstellen, denn die Meldung der beiden Befehle oben ist leicht zu übersehen:

```bash
az role assignment list --assignee-object-id $PRINCIPAL --all --output table
```

Es müssen **zwei Zeilen** erscheinen: `AcrPull` auf Eurer Registry und `Storage Blob Data Contributor` auf Eurem Speicherkonto. Ist die Liste **leer**, oder meldete der Befehl `AuthorizationFailed ... roleAssignments/write`, darfst Du keine Rollen vergeben.
Mit der Rolle *Mitwirkender* (Contributor) kannst Du Ressourcen anlegen, aber **keine Rollen vergeben**. Dafür braucht es *Besitzer*, *Benutzerzugriffsadministrator* oder (nach meinem Kenntnisstand, mit eingeschränkten Rechten) *Role Based Access Control Administrator* auf der Ressourcengruppe.
Ohne diese Rollen kann die App ihr Image nicht laden (`ACRTokenRetrievalFailure` im Protokoll) und keine Dokumente speichern.

**Weg 1 (richtig): Die IT vergibt die zwei Rollen.** Gib ihr diese Angaben (Werte mit den Befehlen darunter auslesen):

> Bitte folgende Rollenzuweisungen vergeben. Prinzipal: Managed Identity der Web-App `<APP>`, Objekt-ID `<PRINCIPAL>`, Typ *ServicePrincipal*.
> 1. Rolle **AcrPull** auf der Container Registry `<ACR>` (Ressourcen-ID `<ACR_ID>`)
> 2. Rolle **Storage Blob Data Contributor** auf dem Speicherkonto `<SA>` (Ressourcen-ID `<SA_ID>`)

```bash
echo "APP=$APP"; echo "PRINCIPAL=$PRINCIPAL"; echo "ACR_ID=$ACR_ID"; echo "SA_ID=$SA_ID"
```

Danach in Deinem Terminal (die Identität bleibt dieselbe, solange Du die Web-App nicht löschst; eine neu angelegte App bekommt eine neue Objekt-ID, dann müssen die Rollen neu vergeben werden):

```bash
az webapp config set --resource-group $RG --name $APP --acr-use-identity true --acr-identity '[system]'
az webapp restart --resource-group $RG --name $APP
```

**Weg 2 (nur zum Testen, bis die Rollen da sind): Zugangsdaten statt Rollen.** Das geht mit *Mitwirkender*, legt aber **Geheimnisse in den App-Einstellungen** ab, die jeder mit Leserecht auf die App sehen kann, und kann durch eine Richtlinie gesperrt sein. Wechsle auf die Rollen (Weg 1), sobald sie da sind.

```bash
az acr update --name $ACR --admin-enabled true
ACR_USER=$(az acr credential show --name $ACR --query username --output tsv)
ACR_PASS=$(az acr credential show --name $ACR --query "passwords[0].value" --output tsv)

az webapp config set --resource-group $RG --name $APP --acr-use-identity false
az webapp config container set --resource-group $RG --name $APP \
  --container-image-name $ACR.azurecr.io/servicecheck:1 \
  --docker-registry-server-url https://$ACR.azurecr.io \
  --docker-registry-server-user "$ACR_USER" --docker-registry-server-password "$ACR_PASS"

CONN=$(az storage account show-connection-string --resource-group $RG --name $SA --query connectionString --output tsv)
az webapp config appsettings set --resource-group $RG --name $APP --settings AZURE_STORAGE_CONNECTION_STRING="$CONN"
az webapp restart --resource-group $RG --name $APP
```

Der Verbindungsstring (Schlüssel des Speicherkontos) setzt voraus, dass der Schlüsselzugriff am Speicherkonto nicht gesperrt ist. Nach dem Wechsel auf Weg 1:

```bash
az acr update --name $ACR --admin-enabled false
az webapp config appsettings delete --resource-group $RG --name $APP --setting-names AZURE_STORAGE_CONNECTION_STRING
az webapp config set --resource-group $RG --name $APP --acr-use-identity true --acr-identity '[system]'
az webapp restart --resource-group $RG --name $APP
```

## Schritt 13 – Web-App ans Netz hängen, Einstellungen setzen, testen

Hast Du seit Schritt 10 ein **neues Terminal** geöffnet, stelle zuerst die abgeleiteten Werte (`PG_HOST`, `DATABASE_URL`, Netz-IDs) wieder her: Anhang E.

Die **VNet-Integration** schickt die ausgehenden Verbindungen der App (Datenbank, Blob) durch das Netz:

```bash
az webapp vnet-integration add --resource-group $RG --name $APP --vnet $VNET_ID --subnet $SUBNET_APP_ID
```

Prüfe vor den Einstellungen, dass **alle** Variablen gefüllt sind. Eine leere Variable würde als leere App-Einstellung gespeichert, und die App startet nicht (`DATABASE_URL ist leer oder ungültig`):

```bash
for v in DATABASE_URL SECRET_KEY ADMIN_PASSWORD PGPASS SA APP RG PG_HOST VNET_ID SUBNET_APP_ID; do eval "val=\${$v}"; [ -z "$val" ] && echo "FEHLT: $v"; done; echo "Prüfung beendet"
```

Steht vor „Prüfung beendet“ **kein** `FEHLT:`, setzt Du die Einstellungen und startest neu:

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

az webapp log config --resource-group $RG --name $APP --docker-container-logging filesystem
az webapp restart --resource-group $RG --name $APP
```

(`SEED_DEMO_DATA=1` legt zum Testen einen Beispielkatalog an, sofern noch gar kein Managed Service existiert.) Verbindungen zu privaten Adressen (hier `10.163.13.x`) laufen automatisch durch das Netz.

Die Web-App ist an dieser Stelle **noch öffentlich erreichbar**, damit Du Datenbank und Dokumente zuerst testen kannst. Der erste Start dauert 2 bis 5 Minuten (Image laden, Datenbank-Migration):

```bash
curl https://$APP.azurewebsites.net/api/health
```

Erwartet: `{"status":"ok"}`. Öffne die Adresse im Browser, melde Dich mit **`admin`** und Deinem `ADMIN_PASSWORD` an, lege einen Kunden und ein Onboarding an und klicke **„PDF ablegen“**.

**Kein Onboarding möglich?** Mit `SEED_DEMO_DATA=0` gibt es noch **keinen Katalog**, und ein Onboarding braucht ein Produkt. Entweder legst Du unter *Kataloge & Vorlagen* einen Managed Service mit einem Produkt an (jedes neue Produkt bekommt eine Standard-Onboarding-Vorlage), oder Du schaltest für den Test den Beispielkatalog ein.
Er wird beim Start nur angelegt, solange noch gar kein Managed Service existiert:

```bash
az webapp config appsettings set --resource-group $RG --name $APP --settings SEED_DEMO_DATA=1
az webapp restart --resource-group $RG --name $APP
```

Danach setzt Du `SEED_DEMO_DATA=0` zurück (gleicher Befehl mit `0`, danach Neustart). Bereits angelegte Daten bleiben erhalten.
sollte im Portal unter Speicherkonto → Container `documents` ein Blob unter `onboardings/…` liegen. Optional (empfohlen): Im Portal unter Web-App → Überwachung → **Integritätsprüfung** den Pfad `/api/health` eintragen.

Läuft die App nicht: `az webapp log tail --resource-group $RG --name $APP` (solange sie noch öffentlich ist) und die Fehlersuche in Anhang B.

## Schritt 14 – Eingang der Web-App über Private Endpoint

```bash
APP_ID=$(az webapp show --resource-group $RG --name $APP --query id --output tsv)

az network private-endpoint create --resource-group $RG --name pe-app --subnet $SUBNET_PE_ID \
  --private-connection-resource-id $APP_ID --group-id sites --connection-name pe-app-conn

az network private-endpoint dns-zone-group create --resource-group $RG --endpoint-name pe-app \
  --name default --private-dns-zone $ZONE_APP --zone-name sites
```

Der Private Endpoint gilt auch für die Verwaltungsadresse der App (`$APP.scm.azurewebsites.net`, Logs und Terminal). Prüfe wie in Schritt 11 mit `az network private-endpoint list --resource-group $RG --output table`, dass `pe-app` existiert.

## Schritt 15 – Privaten Zugang testen, bevor der öffentliche abgeschaltet wird

Du brauchst einen Rechner **im** virtuellen Netz. Am einfachsten ist eine kleine, kurzlebige Linux-VM ohne öffentliche Adresse in einer eigenen Ressourcengruppe, die Du über die Azure-Verwaltung steuerst (ohne SSH).

**VM-Größe:** Die frühere B-Serie (`Standard_B1s`, Familie *Standard BS*, Bv1) ist im Portal als **End of Life** gekennzeichnet. Welche neueren Größen in Eurer Region verfügbar sind, zeigt:

```bash
az vm list-sizes --location $LOC --query "[?starts_with(name,'Standard_B') && contains(name,'_v2')].name" --output tsv
```

Nimm eine **ohne `p` im Namen** (mit `p` sind es Arm-Prozessoren, auf denen das Ubuntu-Abbild unten nicht läuft), z. B. `Standard_B2ts_v2` oder `Standard_B2ats_v2`, und setze `VM_SIZE` in `~/azure.env` entsprechend.

```bash
RG_TEST=rg-servicecheck-test
az group create --name $RG_TEST --location $LOC

az vm create --resource-group $RG_TEST --name vm-nettest \
  --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest --size $VM_SIZE \
  --subnet $SUBNET_PE_ID --public-ip-address "" --nsg-rule NONE \
  --admin-username azureuser --generate-ssh-keys

az vm run-command invoke --resource-group $RG_TEST --name vm-nettest --command-id RunShellScript \
  --scripts "getent hosts $APP.azurewebsites.net; curl -s https://$APP.azurewebsites.net/api/health"
```

Erwartet: Der Name löst auf eine Adresse im Bereich **10.163.13.68 bis .94** (Subnetz `snet-pe`) auf, und die Antwort ist `{"status":"ok"}`. Steht dort eine öffentliche Adresse, ist die DNS-Zone nicht (richtig) mit dem Netz verknüpft (Schritt 9 und 14 prüfen).
Ist die gewünschte Größe in Eurer Region nicht verfügbar, wähle eine andere.

## Schritt 16 – Öffentlichen Zugang der Web-App abschalten

**Nur wenn Schritt 15 ein richtiges Ergebnis geliefert hat.** Ab jetzt kommt von außen niemand mehr an die App, auch Du nicht:

```bash
az webapp update --resource-group $RG --name $APP --set publicNetworkAccess=Disabled
```

Prüfen: Aus dem Internet (Dein Mac ohne Netzanbindung) liefert `curl https://$APP.azurewebsites.net/api/health` jetzt eine Fehlermeldung (HTTP 403), aus der Test-VM weiterhin `{"status":"ok"}`:

```bash
az vm run-command invoke --resource-group $RG_TEST --name vm-nettest --command-id RunShellScript \
  --scripts "curl -s https://$APP.azurewebsites.net/api/health"
```

Kommst Du nach diesem Schritt nicht mehr an die App, ist das Absicht. Mit `--set publicNetworkAccess=Enabled` machst Du den Schritt rückgängig. Die Test-VM löschst Du, wenn Du sie nicht mehr brauchst (Anhang C).

## Schritt 17 – Zugang für Eure Benutzer (mit der IT)

Das Azure-Ende ist fertig. Damit Eure Mitarbeiter die App öffnen können, muss die IT zwei Dinge einrichten. Die Befehle hängen von Eurer Umgebung ab:

1. **Netzwerkverbindung** zwischen Firmennetz und dem virtuellen Netz `10.163.13.0/24`: Site-to-Site-VPN, ExpressRoute, Peering zu einem vorhandenen Hub-Netz oder ein VPN pro Benutzer (Point-to-Site) in dieses Netz.
2. **Namensauflösung:** Der Name `$APP.azurewebsites.net` muss bei den Arbeitsplätzen auf die **private** Adresse zeigen. Üblich ist eine bedingte Weiterleitung (Conditional Forwarder) im Firmen-DNS für `azurewebsites.net` an einen DNS-Resolver im virtuellen Netz (z. B. Azure DNS Private Resolver), der die private Zone aus Schritt 9 kennt.
   Einfacher und empfohlen ist ein interner Eintrag mit eigenem Namen (z. B. `servicecheck.firma.de`) auf die private IP, siehe **17.1**. Dann braucht Ihr keine Weiterleitung für `azurewebsites.net`, die Adresse ist kurz und gehört Euch.

Die Anmeldung über Entra ID bleibt davon im Browser unberührt: Der Benutzer muss die App-Adresse und `login.microsoftonline.com` erreichen können. **Die App selbst muss ausgehend ebenfalls `login.microsoftonline.com` (TCP 443) erreichen.** Das ist nur dann automatisch so, wenn der ausgehende Verkehr der App nicht durch eine Firewall läuft. Mit `vnetRouteAllEnabled=true` (Schritt 13) geht aller Verkehr durch Euer Netz und damit durch Eure Firewall: Dort muss die Freigabe **`snet-app` → `login.microsoftonline.com`, TCP 443** (FQDN-Regel) stehen, siehe Schritt 18 und Anhang A.

### 17.1 Eigener interner Name mit Zertifikat (empfohlen)

Voraussetzungen: eine **öffentlich registrierte Domain**, bei der Ihr einen TXT-Eintrag setzen könnt (nur einmalig, für die Besitzprüfung), ein **internes DNS**, in dem Ihr einen A-Record anlegen könnt, und ein **Zertifikat** (PFX) für den Namen. Die kostenlosen, von Azure verwalteten Zertifikate gehen für eine nicht öffentlich erreichbare App nicht.

**1. Namen festlegen** (hier als Beispiel):

```bash
source ~/azure.env
APP_HOST=servicecheck.firma.de
```

**2. Besitzprüfung: TXT-Eintrag im öffentlichen DNS.** Hole die Verification-ID der App:

```bash
az webapp show --resource-group $RG --name $APP --query customDomainVerificationId --output tsv
```

Lege im **öffentlichen** DNS der Domain einen Eintrag an: Typ `TXT`, Name `asuid.servicecheck` (bei manchen Oberflächen der volle Name `asuid.servicecheck.firma.de`), Wert = die ID (ohne Anführungszeichen). Ein A-Record oder CNAME für `servicecheck` im öffentlichen DNS ist **nicht** nötig. Der Name soll von außen nicht auflösbar sein. Prüfen, dass der Eintrag öffentlich sichtbar ist:

```bash
nslookup -type=TXT asuid.servicecheck.firma.de 8.8.8.8
```

Der TXT-Eintrag wird nur beim Anlegen der Bindung gebraucht.

**3. Hostnamen an die App binden:**

```bash
az webapp config hostname add --webapp-name $APP --resource-group $RG --hostname $APP_HOST
az webapp config hostname list --webapp-name $APP --resource-group $RG --output table
```

**4. Internes DNS:** A-Record `$APP_HOST` auf die **private IP des Private Endpoints** der App (Schritt 14). Die Adresse liest Du so aus:

```bash
az network nic show --ids $(az network private-endpoint show --resource-group $RG --name pe-app --query "networkInterfaces[0].id" --output tsv) \
  --query "ipConfigurations[0].privateIPAddress" --output tsv
```

Bis der Eintrag steht, kannst Du auf einem Windows-Rechner im Netz testweise in `C:\Windows\System32\drivers\etc\hosts` die Zeile `<private IP> servicecheck.firma.de` eintragen (als Administrator, danach wieder entfernen).

**5. Zertifikat hochladen und binden.** Das Zertifikat kommt als **PFX mit privatem Schlüssel** aus Eurer internen CA (oder von einer öffentlichen CA). Anforderungen:

- passwortgeschützt, mit Triple-DES verschlüsselt (neuere OpenSSL-Versionen verschlüsseln anders: bei Fehlern beim Hochladen das PFX neu exportieren oder mit `-legacy` umwandeln),
- privater Schlüssel enthalten, dazu **Zwischenzertifikate und Root** in der Kette,
- Verwendung **Serverauthentifizierung** (Extended Key Usage 1.3.6.1.5.5.7.3.1),
- der Name `servicecheck.firma.de` als **SAN** (nicht nur im CN),
- RSA mit mindestens 2048 Bit ist der sichere Weg. ECC-Zertifikate nimmt App Service laut Microsoft-Doku an, **nur als PFX-Upload** (nicht aus Key Vault). Über zulässige Kurven und Mindestlängen sagt die Doku nichts. Bei ECC also zuerst testen.

```bash
THUMB=$(az webapp config ssl upload --resource-group $RG --name $APP \
  --certificate-file ~/Downloads/servicecheck.pfx --certificate-password 'PFX-PASSWORT' --query thumbprint --output tsv)
az webapp config ssl bind --resource-group $RG --name $APP --certificate-thumbprint $THUMB --ssl-type SNI
az webapp config ssl list --resource-group $RG --output table
```

Ein Neustart ist dafür **nicht** nötig. Ohne Zertifikat funktioniert der Name bereits, der Browser zeigt aber eine Warnung („Name stimmt nicht überein“), weil dann das Standardzertifikat von `*.azurewebsites.net` ausgeliefert wird.

**6. Prüfen** (im Firmennetz, auf einem Gerät, das der CA vertraut): `https://servicecheck.firma.de/api/health` muss **ohne Zertifikatswarnung** `{"status":"ok"}` liefern. Auf dem Mac und anderen Geräten ohne Domäne muss die CA-Root vorher installiert werden.

**Zertifikat erneuern:** Die Laufzeit steht im Zertifikat. Trag das Ablaufdatum in einen Kalender ein. Zum Erneuern wiederholst Du Punkt 5 mit dem neuen PFX. Das Zertifikat kann auf demselben Hostnamen ausgetauscht werden.

Ab jetzt verwendest Du in **Schritt 18** `https://$APP_HOST/...` als Adresse.

## Schritt 18 – Anmeldung mit Entra ID einrichten

Diese Schritte erfolgen im **Entra-Admin-Center** (https://entra.microsoft.com), nicht im Terminal. Wenn Du keine Rechte hast, gib sie Deiner IT mit.

1. **Identität → Anwendungen → App-Registrierungen → Neue Registrierung.**
   - Name: `Service Check`
   - Unterstützte Kontotypen: **Nur Konten in diesem Organisationsverzeichnis** (Einzelmandant)
   - Umleitungs-URI: Plattform **Web**, Wert `https://<APP_HOST>/api/auth/oidc/callback` (mit Deinem eigenen Namen aus Schritt 17.1, sonst `<APP>.azurewebsites.net`)
   - **Registrieren**
2. Auf der Übersichtsseite notierst Du **Anwendungs-ID (Client)** und **Verzeichnis-ID (Mandant)**.
3. **Zertifikate & Geheimnisse → Neuer geheimer Clientschlüssel.** Ablauf 12 oder 24 Monate. Den **Wert** sofort kopieren, er wird nur einmal angezeigt. Trage das Ablaufdatum in einen Kalender ein. Danach ist die Anmeldung kaputt, bis ein neuer Schlüssel in der App hinterlegt ist.
4. **App-Rollen → App-Rolle erstellen** (zweimal):

   | Anzeigename | Zulässige Mitgliedstypen | Wert | Beschreibung |
   |---|---|---|---|
   | Service Check Administrator | Benutzer/Gruppen | `ServiceCheck.Admin` | Pflegt Kataloge, Vorlagen und Benutzer |
   | Service Check Consultant | Benutzer/Gruppen | `ServiceCheck.Consultant` | Führt Service Checks und Onboardings durch |

5. **Unternehmensanwendungen → Service Check → Eigenschaften:** **„Zuweisung erforderlich?“ = Ja**, speichern. Dann kann sich nur anmelden, wer zugewiesen ist.
6. **Unternehmensanwendungen → Service Check → Benutzer und Gruppen → Benutzer/Gruppe hinzufügen:** Benutzer oder Gruppen auswählen und jeweils eine Rolle zuweisen. (Gruppen lassen sich nur mit einer Entra-ID-P1/P2-Lizenz zuweisen, sonst einzelne Benutzer.) Weise **Dir selbst** zuerst `Service Check Administrator` zu.
7. Zurück im Terminal die Werte in der App hinterlegen. Setze die Variablen **im Terminal**, nicht in `azure.env` (der Clientschlüssel ist ein Geheimnis):

```bash
TENANT_ID="<Verzeichnis-ID aus Punkt 2>"
CLIENT_ID="<Anwendungs-ID aus Punkt 2>"
CLIENT_SECRET="<Wert des Clientschlüssels aus Punkt 3>"
APP_HOST="${APP_HOST:-$APP.azurewebsites.net}"   # eigener Name aus Schritt 17.1, sonst der Standardname

az webapp config appsettings set --resource-group $RG --name $APP --settings \
  OIDC_TENANT_ID="$TENANT_ID" \
  OIDC_CLIENT_ID="$CLIENT_ID" \
  OIDC_CLIENT_SECRET="$CLIENT_SECRET" \
  OIDC_REDIRECT_URI="https://$APP_HOST/api/auth/oidc/callback"

az webapp restart --resource-group $RG --name $APP
```

Die Umleitungs-URI in Entra und `OIDC_REDIRECT_URI` müssen **zeichengleich** sein.

**Zwei Stolpersteine bei der Entra-Einrichtung:**

- **Einwilligung des Administrators:** Verlangt Euer Tenant eine Genehmigung („Approval required“), erteilt ein Administrator unter **App-Registrierungen → Service Check → API-Berechtigungen → Administratoreinwilligung erteilen**. Die App braucht nur Microsoft Graph `User.Read` (delegiert, `openid`, `profile`, `email`).
- **Ausgehende Freigabe der App:** Die App holt das Token **serverseitig** bei `login.microsoftonline.com` ab. Ist das durch die Firewall blockiert, meldet der Browser nach der Microsoft-Anmeldung einen nackten **Internal Server Error**, und im Protokoll steht `httpx.ConnectError`. Siehe Anhang B.

Danach steht auf der Anmeldeseite **„Mit Microsoft anmelden“**. Melde Dich damit an (aus dem Netz, Schritt 17). Unter „Benutzer“ erscheint Dein Konto mit dem Hinweis **SSO**. Rolle und Name kommen ab sofort aus Entra und werden bei jeder Anmeldung aktualisiert.

## Schritt 19 – Lokale Anmeldung abschalten (empfohlen)

Erst wenn die Microsoft-Anmeldung als Administrator funktioniert:

```bash
az webapp config appsettings set --resource-group $RG --name $APP --settings AUTH_LOCAL_ENABLED=0
az webapp restart --resource-group $RG --name $APP
```

Ab dann gibt es keine Passwort-Anmeldung mehr. Wenn die Entra-Anmeldung einmal nicht funktioniert, setzt Du `AUTH_LOCAL_ENABLED=1` wieder und meldest Dich als `admin` an. Das geht nur, wenn die lokale Anmeldung mindestens einmal aktiv war (der Standard-Administrator wird beim allerersten Start angelegt).

## Schritt 20 – Datensicherung und Wiederherstellung

| Was | Wie | Aufbewahrung |
|---|---|---|
| Datenbank | automatische Sicherung des Flexible Servers, Wiederherstellung auf Zeitpunkt | 35 Tage (Schritt 10) |
| Dokumente (PDFs) | Blob-Versionierung und Soft Delete | 30 Tage nach dem Löschen (Schritt 8) |
| Entra-Rollenzuweisungen | liegen in Entra ID, nicht in der App | – |
| Optional: unabhängige Kopie der Datenbank | `scripts/backup.sh` (pg_dump), **nur von einem Rechner im Netz** (z. B. kleine VM oder Bastion) in ein **anderes** Speicherkonto | frei wählbar |

Einstellung prüfen:

```bash
az postgres flexible-server show --resource-group $RG --name $PG --query backup
```

**Wiederherstellung üben** (vor dem Produktivstart einmal, danach z. B. halbjährlich). Die Wiederherstellung legt einen **neuen** Server an, mit privatem Ziel (`SUBNET_DB_ID` und `ZONE_PG_ID` stellst Du in einem neuen Terminal mit Anhang E wieder her):

```bash
az postgres flexible-server restore \
  --resource-group $RG --name $PG-restore --source-server $PG \
  --restore-time "2026-11-10T08:00:00Z" \
  --subnet $SUBNET_DB_ID --private-dns-zone $ZONE_PG_ID
```

Der Zeitpunkt (UTC) muss in der Vergangenheit und innerhalb der Aufbewahrungszeit liegen. Um die App auf den neuen Server umzustellen, liest Du dessen `fullyQualifiedDomainName` aus (wie in Schritt 10), setzt `DATABASE_URL` neu und startest die App neu. Den Übungsserver löschst Du danach wieder
(`az postgres flexible-server delete --resource-group $RG --name $PG-restore --yes`).

**Gelöschtes Dokument zurückholen** (aus dem Netz, oder im Portal, denn der öffentliche Zugang des Speicherkontos ist aus):

```bash
az storage blob undelete --account-name $SA --container-name documents --name "onboardings/<ID>/<Datei>.pdf" --auth-mode login
```

Den Blob-Namen findest Du im Portal unter Speicherkonto → Container `documents` (Ansicht „Gelöschte Blobs anzeigen“).

**Wichtig:** Nach einer zeitpunktgenauen Wiederherstellung der Datenbank können Dokument-Blobs existieren, die in der Datenbank nicht mehr referenziert sind, oder Datenbankeinträge ohne Blob, wenn das Blob nach dem gewählten Zeitpunkt gelöscht wurde. Blob-Versionen und Soft Delete helfen beim Zurückholen.

## Schritt 21 – Updates einspielen

Neuen Stand holen, neues Image **in Azure** bauen, App darauf umstellen. Die Befehle laufen über öffentliche Adressen bzw. die Azure-Verwaltung, es ist keine Netzanbindung nötig, **solange der öffentliche Zugang der Web-App nicht abgeschaltet ist** (Schritt 16). Danach brauchst Du für Logs den Zugang aus dem Netz, für den Image-Bau und die Umstellung weiterhin nicht.

**1. Aktuellen Stand holen** (im Ordner des Repositories auf dem Mac, auf dem Branch, den Ihr verwendet):

```bash
BRANCH=main        # der Branch mit dem neuen Stand, falls Ihr einen anderen verwendet: hier eintragen
cd ServiceCheckWebApp
git fetch origin
git checkout $BRANCH
git pull
```

**2. Aktuelles Tag ermitteln und um eins erhöhen:**

```bash
source ~/azure.env
az webapp config show --resource-group $RG --name $APP --query linuxFxVersion --output tsv
```

Die Ausgabe sieht aus wie `DOCKER|<registry>.azurecr.io/servicecheck:1`. Das Tag hinter dem Doppelpunkt ist der laufende Stand. Setze das nächste:

```bash
TAG=2    # eine Zahl höher als das laufende Tag
```

**3. Image bauen, umstellen, neu starten:**

```bash
az acr build --registry $ACR --image servicecheck:$TAG --file Dockerfile .
az webapp config container set --resource-group $RG --name $APP --container-image-name $ACR.azurecr.io/servicecheck:$TAG
az webapp restart --resource-group $RG --name $APP
```

Den Befehl `az acr build` führst Du im Hauptordner des Repositories aus (dort liegt das `Dockerfile`); der Punkt am Ende ist der Ordner. Der Bau dauert einige Minuten. Beim ersten Aufruf nach dem Neustart braucht die App ein paar Sekunden zum Starten.

**4. Prüfen:** Die App öffnen (`https://$APP_HOST` aus dem Netz) und die geänderte Stelle ansehen. Im Browser notfalls mit Strg+F5 neu laden, damit keine alte Oberfläche aus dem Cache kommt.

Datenbankänderungen laufen beim Start automatisch als Migration, bestehende Daten bleiben erhalten. Erhöhe das Tag bei jedem Update, damit klar ist, was läuft, und Du bei Problemen mit `config container set … servicecheck:<altes Tag>` plus Neustart auf den vorherigen Stand zurückstellen kannst. **Vor größeren Updates** machst Du zusätzlich eine
Datenbanksicherung (`scripts/backup.sh`, aus dem Netz) oder notierst wenigstens den Wiederherstellungszeitpunkt. Eine **Migration lässt sich nicht automatisch zurücknehmen**: Nach einem Zurückstellen des Images bleibt die Datenbank im neuen Stand, was bei reinen Spaltenergänzungen unkritisch ist.

**Logs:** Solange der öffentliche Zugang an ist, holst Du sie von jedem Rechner aus: Einmal die Protokollierung einschalten, dann herunterladen:

```bash
az webapp log config --resource-group $RG --name $APP --docker-container-logging filesystem
az webapp log download --resource-group $RG --name $APP --log-file ~/applogs.zip
unzip -o ~/applogs.zip -d ~/applogs
grep -rhiE "Traceback|Error|Timeout" ~/applogs | tail -40
```

Nach Schritt 16 brauchen `az webapp log tail`, der Download und das Portal-Logstream die Verwaltungsadresse der App und funktionieren **nur noch aus dem Netz**. Empfohlen für den Dauerbetrieb: die App-Logs an einen Log-Analytics-Arbeitsbereich senden (Diagnoseeinstellungen), den Du im Portal einsehen kannst.

---

## Anhang A – Welche Ports zwischen den Subnetzen nötig sind

**Wie die Anleitung geschrieben ist, legt Ihr keine Netzwerksicherheitsgruppen (NSGs) an.** Dann ist der gesamte Verkehr innerhalb des virtuellen Netzes erlaubt, und alles funktioniert ohne Portregeln. Schreibt Eure IT NSGs vor, braucht Ihr diese Freigaben:

| Von | Nach | Port | Wofür |
|---|---|---|---|
| `snet-app` (Web-App, ausgehend) | `snet-db` (PostgreSQL) | **TCP 5432** | Datenbankzugriff |
| `snet-app` | `snet-pe` (Private Endpoint Blob) | **TCP 443** | Dokumente ablegen und abrufen |
| Firmennetz / VPN-Benutzer | `snet-pe` (Private Endpoint Web-App) | **TCP 443** | App im Browser aufrufen |
| Firmennetz / VPN-Benutzer | `snet-pe` | TCP 80 (optional) | nur für die Weiterleitung von `http://` auf `https://` |
| Administrator-Rechner im Netz | `snet-db` | TCP 5432 | `psql` und `scripts/backup.sh` |
| Administrator (aus dem Netz) | `snet-pe` (Verwaltungsadresse der Web-App) | TCP 443 | Logs und App-Terminal |
| `snet-app` | Internet, `login.microsoftonline.com` | **TCP 443** | Entra-Anmeldung (Token abholen, Schlüssel prüfen). Das Diensttag `AzureActiveDirectory` deckt das ab |
| `snet-app`, `snet-db`, `snet-pe` | Azure-DNS `168.63.129.16` | UDP/TCP 53 | Namensauflösung. **Nicht blockieren** |

- `snet-app` braucht **keinen eingehenden** Verkehr. Die VNet-Integration ist rein ausgehend.
- **Private Endpoints und NSGs:** Standardmäßig gelten NSG-Regeln für Private Endpoints **nicht**. Willst Du den Zugriff darauf per NSG begrenzen, muss das Subnetz `snet-pe` mit `--private-endpoint-network-policies Enabled` angelegt sein.
- Beschränkst Du innerhalb des Netzes den Verkehr, brauchst Du explizite Sperrregeln. Die Standardregeln einer NSG erlauben den Verkehr im virtuellen Netz.
- **Datenbank-Subnetz:** Schränke hier ausgehend nichts ein, ohne die aktuellen Microsoft-Vorgaben für delegierte PostgreSQL-Subnetze zu prüfen. Nach meinem Kenntnisstand gibt es Abhängigkeiten zu Azure-Diensten.
- **Container Registry:** Das Image zieht die Plattform von der öffentlichen Registry, dafür brauchst Du keine Regel in Deinem Netz.
- Eine zentrale Firewall im Hub-Netz bringt eigene Regeln mit.

## Anhang B – Fehlersuche

| Symptom | Mögliche Ursache und Abhilfe |
|---|---|
| Zeilenweise `zsh: command not found: #` oder Variable bleibt leer | In der zsh sind Kommentare beim Einfügen nicht aktiv: `setopt interactive_comments` (Schritt 2.3) |
| `SyntaxWarning: "\/" is an invalid escape sequence` | Harmlose Warnung der Azure-CLI auf neuem Python, keine Fehlermeldung. Mit `export PYTHONWARNINGS=ignore` ausblenden |
| `MissingSubscriptionRegistration` | Dienst-Registrierung fehlt: `az provider register --namespace <Dienst> --wait` (Schritt 4) |
| `AuthorizationFailed` | Dir fehlt eine Rolle auf der Ressourcengruppe (Schritt 1) |
| `LinkedAuthorizationFailed` oder Fehler beim Verwenden des Subnetzes | Dir fehlt auf dem **Netz** in `$RG_NET` die Rolle *Netzwerkmitwirkender* bzw. das Recht `subnets/join/action`. Die IT muss sie vergeben |
| `RequestDisallowedByPolicy` | Eine Azure Policy verbietet die Aktion. Erlaubte Werte (SKU, Region, Tags) aus der Meldung nehmen oder bei der IT eine Ausnahme beantragen. Richtlinien ansehen: `az policy assignment list --disable-scope-strict-match true --query "[].{name:displayName, scope:scope}" --output table` |
| `az appservice plan create`: `Operation cannot be completed without additional quota` | **Kontingent** für die Stufe in der Region ist 0, kein Rechte- oder Richtlinienproblem. Andere Stufe versuchen oder Kontingent beantragen, siehe Schritt 12. Fehlgeschlagene Vorgänge ansehen: `az monitor activity-log list --resource-group $RG --offset 1d --status Failed --output json \| grep -o 'Current Limit ([^)]*): [0-9]*' \| sort -u` |
| `az webapp create`: `Webapp ... already exists ... Unable to retrieve details` | Der Name ist weltweit vergeben (oft durch einen früheren Versuch in einem anderen Abonnement). Neues `SUFFIX` wählen, Schritt 4 |
| Name „bereits vergeben“ bei Registry, Speicherkonto oder Datenbankserver | Neues `SUFFIX` wählen und Variablen neu laden (Schritt 3, 4) |
| `acr build` bricht mit `sh: tsc: Permission denied` (Exit 126) ab | Ein lokales `node_modules` (z. B. von einem anderen Rechner) wurde ins Image kopiert. Mit dem aktuellen Stand nicht mehr möglich: `git pull`, dann `acr build` wiederholen |
| `acr build` schlägt mit Hinweis auf Tasks fehl | ACR Tasks im Abonnement gesperrt, Alternative in Schritt 7 |
| `az postgres flexible-server create` meldet eine fehlerhafte DNS-Zone | Der Zonenname muss auf `.private.postgres.database.azure.com` enden und in `$RG` liegen (oder die volle Ressourcen-ID verwenden) |
| `az postgres flexible-server create`: SKU nicht verfügbar oder Kontingent | Anderes SKU wählen, siehe Schritt 10 (`list-skus`) |
| `ResourceNotFound ... pe-blob` (oder `pe-app`) bei `dns-zone-group create` | Der Private Endpoint wurde nicht angelegt. `az network private-endpoint list --resource-group $RG --output table`, den vorherigen Befehl erneut ausführen und die Fehlermeldung lesen (Schritt 11) |
| `az webapp vnet-integration add` schlägt fehl | Subnetz nicht an `Microsoft.Web/serverFarms` delegiert, oder bereits von einem anderen App-Service-Plan belegt, oder Plan und Netz in verschiedenen Regionen |
| Protokoll (`*_docker.log`): `ACRTokenRetrievalFailure ... Fetching Acr token failed ... Unauthorized` | Der Managed Identity der Web-App fehlt die Rolle `AcrPull` auf der Registry. Rollenliste prüfen (Schritt 12.2). Meist fehlen Dir die Rechte, Rollen zu vergeben, siehe Weg 1 und Weg 2 dort |
| `az role assignment create`: `AuthorizationFailed ... roleAssignments/write` | Mit *Mitwirkender* kannst Du keine Rollen vergeben. Die IT muss sie vergeben (Schritt 12.2, Weg 1) |
| Web-App zeigt „Application Error“ oder 503 | Protokoll lesen (`az webapp log tail`, solange erreichbar). Meist: Image konnte nicht geladen werden (Rolle `AcrPull` noch nicht wirksam, Neustart) oder falsche Einstellungen |
| Log: `DATABASE_URL ist leer oder ungültig` | Die Einstellung ist leer oder falsch aufgebaut. Variablen prüfen (Schritt 13). Eingestellte Werte ansehen, ohne Geheimnisse: `az webapp config appsettings list --resource-group $RG --name $APP --query "[].{name:name, laenge:length(value)}" --output table`. Länge 0 bedeutet leer |
| Log: `SECRET_KEY muss gesetzt sein und mindestens 32 Zeichen haben` oder `ADMIN_PASSWORD muss gesetzt sein` | Einstellung fehlt oder ist zu kurz, Schritt 13 wiederholen. Mit PostgreSQL startet die App sonst absichtlich nicht (`ADMIN_PASSWORD` wird nur beim allerersten Start geprüft) |
| Log: `password authentication failed` | `PGPASS` stimmt nicht mit dem Datenbankpasswort überein: Passwort zurücksetzen (Schritt 3) |
| Log: `could not translate host name` / `Name or service not known` (Datenbank) | Private DNS-Zone der Datenbank nicht mit dem Netz verknüpft (Schritt 9), App nicht in das Netz integriert (Schritt 13) oder `$PG_HOST` falsch (aus `fullyQualifiedDomainName` übernehmen) |
| Log: Timeout zur Datenbank | VNet-Integration fehlt oder zeigt auf das falsche Subnetz, Datenbank-Subnetz nicht an PostgreSQL delegiert (Schritt 6), oder eine NSG blockiert Port 5432 (Anhang A) |
| Log: `Die Datenbank enthält Tabellen, wurde aber nicht mit Migrationen angelegt` | Eine Datenbank aus einer sehr alten Version. Neue, leere Datenbank verwenden |
| Dokument ablegen oder abrufen liefert 503 („Dokumentenspeicher“) | Private Endpoint oder DNS-Zone des Blob-Speichers fehlt (Schritt 9, 11; `getent hosts $SA.blob.core.windows.net` aus dem Netz muss eine Adresse aus 10.163.13.68–.94 liefern), Rolle *Storage Blob Data Contributor* fehlt (Schritt 12), oder `AZURE_STORAGE_ACCOUNT_URL` falsch |
| Browser: „403 – Web App – Unavailable“ oder keine Seite | Der Name zeigt noch auf die öffentliche Adresse (DNS im Firmennetz, Schritt 17), oder die Verbindung ins Netz fehlt |
| `az webapp log tail` hängt oder liefert nichts | Verwaltungsadresse nur im Netz erreichbar (Schritt 21, Logs im privaten Netz) |
| Anmeldeseite: „Für dieses Konto ist keine Rolle vergeben“ | Benutzer ist in Entra keiner App-Rolle zugewiesen (Schritt 18, Punkt 6) |
| Anmeldeseite: „Die Antwort von Microsoft konnte nicht überprüft werden“ / „Anmeldung bei Microsoft fehlgeschlagen“ | `OIDC_TENANT_ID`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` falsch, Clientschlüssel abgelaufen oder Umleitungs-URI weicht ab |
| Microsoft meldet `AADSTS50011` (Antwort-URL stimmt nicht überein) | Umleitungs-URI in der App-Registrierung und `OIDC_REDIRECT_URI` müssen **exakt** gleich sein (Schreibweise, `https`) |
| Microsoft meldet `AADSTS50105` (Benutzer nicht zugewiesen) | Weil „Zuweisung erforderlich“ = Ja: Benutzer der App zuweisen |
| Kein Button „Mit Microsoft anmelden“ | Eine der vier `OIDC_…`-Einstellungen fehlt. Prüfen: `https://$APP_HOST/api/auth/config` (aus dem Netz) muss `"oidc":true` zeigen |
| Nach der Microsoft-Anmeldung **Internal Server Error**; Protokoll: `httpx.ConnectError: [Errno 99] Cannot assign requested address` bei `.../oauth2/v2.0/token` | Die App erreicht `login.microsoftonline.com` ausgehend nicht (Firewall oder Routing). Freigabe `snet-app` → `login.microsoftonline.com`, TCP 443 (FQDN) beantragen. Zum Eingrenzen: `az webapp config set --resource-group $RG --name $APP --vnet-route-all-enabled false` und `az webapp restart` leitet nur noch Verkehr zu privaten Adressen durch das Netz (Datenbank und Speicher bleiben privat, Internetverkehr nimmt den normalen Azure-Weg). Das ist ein Sicherheitskompromiss, den Ihr bewusst entscheidet. Das Protokoll holst Du mit `az webapp log config … --docker-container-logging filesystem` und `az webapp log download` |
| Microsoft meldet `AADSTS900561` („The endpoint only accepts POST requests. Received a GET request.“) | Folgefehler vom **Zurück-Button** des Browsers nach einem Anmeldeschritt, nicht die Ursache. Anmeldung in einem neuen privaten Fenster von der App-Adresse aus neu starten |
| Microsoft-Anmeldung hängt bei „Let's keep your account secure“ | Das ist die MFA-Registrierung Eures Tenants. Mit „Not now“ überspringen, Seite neu laden oder unter `https://aka.ms/mysecurityinfo` eine Methode registrieren. Hat nichts mit der App zu tun |
| `az webapp config hostname add` scheitert mit Hinweis auf eine fehlende Besitzprüfung | Der TXT-Eintrag `asuid.<name>` ist im **öffentlichen** DNS nicht sichtbar oder hat den falschen Wert. Prüfen mit `nslookup -type=TXT asuid.<name> 8.8.8.8` und mit der ID aus `az webapp show … --query customDomainVerificationId` vergleichen |
| Browser zeigt für den eigenen Namen „Name stimmt nicht überein“ | Zertifikat noch nicht gebunden (Schritt 17.1, Punkt 5) oder der Name fehlt als SAN im Zertifikat |
| Hochladen des PFX schlägt fehl | Passwort falsch, privater Schlüssel fehlt oder Verschlüsselung nicht Triple-DES (neuere OpenSSL-Versionen): PFX neu exportieren oder mit `-legacy` umwandeln |

## Anhang C – Aufräumen

Löscht die Test-VM und **alle** Ressourcen der Anwendung unwiderruflich, inklusive Datenbank und Dokumente. Das virtuelle Netz in `$RG_NET` bleibt unberührt, solange Du diese Gruppe nicht löschst:

```bash
az group delete --name $RG_TEST --yes --no-wait
az group delete --name $RG --yes --no-wait
```

Die Test-VM kostet laufend Geld, lösche sie, sobald der Test abgeschlossen ist. Die App-Registrierung in Entra bleibt bestehen und muss dort separat gelöscht werden.
Gibt es noch Ressourcen einer **früheren Bereitstellung** (z. B. in einem anderen Abonnement), prüfe, ob sie noch gebraucht werden. Sie laufen weiter und kosten.

## Anhang D – Empfohlene nächste Schritte für den Dauerbetrieb

- Einen eigenen Datenbankbenutzer mit eingeschränkten Rechten statt des Server-Administrators.
- Geheimnisse (`SECRET_KEY`, `DATABASE_URL`, `OIDC_CLIENT_SECRET`) in einem **Key Vault** ablegen und per Key-Vault-Referenz in die App-Einstellungen einbinden.
- **Netzwerksicherheitsgruppen** je Subnetz nach Anhang A, sofern die IT sie verlangt.
- App-Logs an Log Analytics senden, Warnungen (Azure Monitor) für ausgefallene Integritätsprüfung, Datenbank-Speicher und ablaufenden Clientschlüssel.
- Das Ablaufdatum des Zertifikats (Schritt 17.1) und des Entra-Clientschlüssels (Schritt 18) überwachen.
- Die Ressourcen als Code (Bicep oder Terraform) und eine Pipeline für Updates.
- Zusätzliche, unabhängige Datenbanksicherung (`scripts/backup.sh`) in ein separates Speicherkonto oder Abonnement.
- Vor dem Einsatz mit echten Kundendaten: die offenen Punkte der Datenschutzprüfung (Sicherheits-Header, Schutz vor Passwort-Raten, Auskunfts- und Löschwerkzeuge, Aufbewahrungsfristen, Protokoll) abarbeiten.

## Anhang E – Abgeleitete Werte nach einem neuen Terminal wiederherstellen

`~/azure.env` enthält nur Eure **Eingaben**. Werte, die erst durch die Schritte entstehen (Netz-IDs, Datenbank-URL), gehen mit dem Terminalfenster verloren. Öffnest Du mitten in der Anleitung ein neues Fenster, lädst Du zuerst `source ~/azure.env`
und löst sie dann wieder auf. Werte für Ressourcen, die es noch nicht gibt, bleiben leer, das ist in Ordnung.

```bash
source ~/azure.env
VNET_ID=$(az network vnet show --resource-group $RG_NET --name $VNET --query id --output tsv)
SUBNET_DB_ID=$(az network vnet subnet show --resource-group $RG_NET --vnet-name $VNET --name $SNET_DB --query id --output tsv)
SUBNET_APP_ID=$(az network vnet subnet show --resource-group $RG_NET --vnet-name $VNET --name $SNET_APP --query id --output tsv)
SUBNET_PE_ID=$(az network vnet subnet show --resource-group $RG_NET --vnet-name $VNET --name $SNET_PE --query id --output tsv)
ZONE_PG_ID=$(az network private-dns zone show --resource-group $RG --name $ZONE_PG --query id --output tsv)
SA_ID=$(az storage account show --resource-group $RG --name $SA --query id --output tsv)
PG_HOST=$(az postgres flexible-server show --resource-group $RG --name $PG --query fullyQualifiedDomainName --output tsv)
DATABASE_URL="postgresql+psycopg://$PGADMIN:$PGPASS@$PG_HOST:5432/$DBNAME?sslmode=require"
for v in VNET_ID SUBNET_DB_ID SUBNET_APP_ID SUBNET_PE_ID ZONE_PG_ID SA_ID PG_HOST; do eval "val=\${$v}"; [ -z "$val" ] && echo "FEHLT (noch nicht angelegt?): $v"; done; echo "Prüfung beendet"
```
