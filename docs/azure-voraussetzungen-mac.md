# Voraussetzungen und Einrichtung auf dem Mac

Diese Seite gilt für beide Azure-Anleitungen ([öffentlich](azure-deployment.md) und [mit privatem Netzwerk](azure-deployment-private.md)). Alle Befehle laufen im
**Terminal** des Macs (Programm „Terminal“ oder iTerm). Für die Bereitstellung in Azure brauchst Du **weder Docker noch Python noch Node.js**: Das Image baut Azure
selbst (`az acr build`), und alles andere sind Aufrufe der Azure-CLI.

## Was auf dem Mac vorhanden sein muss

| Was | Wofür | Prüfen | Installieren |
|---|---|---|---|
| **macOS**, aktuelle Version, Intel oder Apple Silicon | Grundlage | `sw_vers` | Systemeinstellungen, Softwareupdate. Bei sehr altem macOS kann die Installation von Homebrew und Azure-CLI scheitern |
| **Administratorrechte** auf dem Mac | Installation von Homebrew | `sudo -v` fragt nach Deinem Passwort | Bei einem Firmen-Mac über die IT. Siehe „Firmen-Mac“ unten |
| **Homebrew** | Paketverwaltung, installiert die Azure-CLI | `brew --version` | Abschnitt „Installation“ |
| **Azure-CLI (`az`)** | alle Azure-Befehle | `az version` | `brew install azure-cli` |
| **`openssl`** | Zufallswerte für Passwörter und Schlüssel | `openssl rand -hex 4` | **ist im Mac enthalten** (LibreSSL), nichts zu tun |
| **`curl`** | App-Test (`/api/health`) | `curl --version` | **ist im Mac enthalten** |
| **`git`** | Quellcode holen, **nur wenn Du das Image neu bauen willst** (Schritt 4) | `git --version` | beim ersten Aufruf bietet macOS die „Command Line Tools“ an, oder `brew install git` |
| **Texteditor** | Datei `azure.env` bearbeiten | `nano --version` | `nano` und `vi` sind enthalten, VS Code ist optional |
| **Webbrowser** | `az login`, Azure-Portal, Entra-Admin-Center | – | z. B. Safari oder Chrome |

**Nicht nötig für die Bereitstellung:** Docker Desktop, Python, Node.js, `winget`, Git Bash, WSL. Python und Node.js brauchst Du nur, wenn Du die App **lokal** auf dem Mac
starten willst (siehe README).

### Was Du außerdem brauchst (kein Programm)

- Ein **Azure-Abonnement** und die Rollen aus Schritt 0 der Hauptanleitung (Besitzer, oder Mitwirkender plus Benutzerzugriffsadministrator, auf der Ressourcengruppe).
- Für die **private Variante:** *Netzwerkmitwirkender* auf der Ressourcengruppe des Netzes (`$RG_NET`) und die Angaben der IT: Name und Ressourcengruppe des Netzes, die drei Subnetze, Region.
- Für die **Entra-Anmeldung (Schritt 9):** Rechte im Entra-Admin-Center, oder die IT erledigt es für Dich.
- Optional, nur für ein **neues Image**: ein GitHub-Zugriffstoken mit Leserecht auf das private Repository (Fine-grained Token, nur dieses Repository, „Contents: read“).
- **Netzwerkzugriff** (ausgehend, HTTPS/443) vom Mac zu: `login.microsoftonline.com`, `management.azure.com`, Eurer Registry `*.azurecr.io` und `github.com` (Quellcode). Für die Installation
  zusätzlich zu `raw.githubusercontent.com` und `github.com` (Homebrew).

## Installation

**1. Homebrew** (einmalig). Das Programm installiert bei Bedarf zuerst die „Command Line Tools“ von Apple und fragt nach Deinem Passwort:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Am Ende zeigt der Installer unter „Next steps“ zwei Zeilen, die Homebrew in den Suchpfad eintragen. **Führe diese Zeilen aus**, sonst findet das Terminal `brew` nicht. Bei Apple Silicon sieht das so aus:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Bei einem Intel-Mac liegt Homebrew unter `/usr/local`, dort steht dann der entsprechende Pfad in der Ausgabe des Installers.

**2. Azure-CLI:**

```bash
brew update
brew install azure-cli
```

**3. Git** (nur für ein neues Image): Rufe `git --version` auf. Fragt macOS nach den „Command Line Tools“, bestätige. Alternativ: `brew install git`.

**4. Aktuell halten:** Die Befehle der Anleitungen sind gegen die Azure-CLI 2.91 abgeglichen. Eine neuere Version ist unproblematisch.

```bash
brew upgrade azure-cli
```

## Die Shell: zsh richtig einstellen (wichtig)

Das Terminal des Macs benutzt **zsh**. Eine zsh verhält sich in einem Punkt anders, der die Anleitungen betrifft, wenn Du Blöcke **einfügst**:

- Kommentare mit `#` gelten in der interaktiven zsh **nicht als Kommentar**. Aus `RG='meine-gruppe'   # Name der Gruppe` wird ein anderer Befehl, und **die Variable wird nicht gesetzt**,
  ohne dass eine klare Fehlermeldung erscheint. Aus einer Zeile, die nur aus einem Kommentar besteht, wird `zsh: command not found: #`.

Behebe das **einmalig und dauerhaft**:

```bash
echo 'setopt interactive_comments' >> ~/.zshrc
source ~/.zshrc
```

Für ein bereits offenes Terminal reicht auch `setopt interactive_comments`. Danach funktionieren die Blöcke der Anleitungen unverändert. Die Prüfschleifen sind so geschrieben, dass sie in zsh und in bash laufen.
Alternativ startest Du mit `bash` eine Bash-Sitzung (macOS zeigt dazu einen Hinweis zur zsh an, den Du ignorieren kannst).

## Variablen: Datei statt Einfügen

Pro Terminalfenster gehen Variablen verloren. Lege sie deshalb **einmal** in einer Datei ab und lade sie in jedem Terminal:

```bash
cp docs/azure.env.example ~/azure.env       # aus dem Projektordner heraus; ohne Code: Inhalt der Vorlage in nano einfügen
chmod 600 ~/azure.env                       # nur Du darfst die Datei lesen
nano ~/azure.env                            # Werte eintragen: speichern mit Control+O, Enter; beenden mit Control+X
source ~/azure.env
```

Die Datei steht in Deinem Benutzerordner, **nicht** im Projekt, und gehört nicht in Git. Geheimnisse (`PGPASS`, `SECRET_KEY`, `ADMIN_PASSWORD`) erzeugst Du **einmal**
(`openssl rand -hex 16` bzw. `-hex 32`), trägst sie in die Datei ein und speicherst sie zusätzlich im Passwort-Manager. In der Vorlage werden sie nicht bei jedem Laden neu gewürfelt.

Die Prüfung, ob alles gefüllt ist, steht in der Vorlage und in den Anleitungen.

## Prüfen, ob der Mac bereit ist

```bash
for t in brew az openssl curl git; do
  if command -v $t >/dev/null 2>&1; then echo "OK      $t"; else echo "FEHLT   $t"; fi
done
echo "Shell: $SHELL"
openssl rand -hex 4 >/dev/null 2>&1 && echo "OK      openssl rand" || echo "FEHLT   openssl rand"
az version --query '"azure-cli"' --output tsv 2>/dev/null
```

Erwartet: `OK` für `brew`, `az`, `openssl`, `curl` (`git` nur für ein neues Image), `Shell: /bin/zsh` und eine Versionsnummer der Azure-CLI. Fällt `openssl rand` aus, nimm diese Alternative statt
`openssl rand -hex 16`: `LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 32`.

## Anmelden

```bash
az login
az account list --output table
az account set --subscription "Name oder ID Deines Abonnements"
az account show --query "{Abo:name, Mandant:tenantId}" --output table
```

`az login` öffnet den Browser. Geht das nicht (z. B. gesperrter Browser), nimm `az login --use-device-code` und gib den angezeigten Code auf der Seite https://microsoft.com/devicelogin ein.

## Firmen-Mac

- **Homebrew blockiert oder keine Administratorrechte:** Dann nutze die **Azure Cloud Shell** (Bash im Browser, https://shell.azure.com). Dort sind `az`, `openssl`, `curl` und `git` schon vorhanden, und Du bist bereits
  angemeldet. Alle Anleitungen laufen dort unverändert. Beachte, dass Variablen nach etwa 20 Minuten Inaktivität verloren gehen (Datei `~/azure.env` benutzen).
- **Proxy oder TLS-Prüfung** (Zertifikatsfehler bei `az`): Nach Microsofts Dokumentation setzt Du den Pfad zum Firmenzertifikat, z. B. `export REQUESTS_CA_BUNDLE=/pfad/zum/firmenzertifikat.pem`. Schalte die
  Zertifikatsprüfung **nicht** ab. Fragt Eure IT nach dem Zertifikat.
- **Private Variante:** Von Deinem Mac erreichst Du die private Web-App und die private Datenbank nur über die Netzanbindung Eurer Firma. Die Anleitung verwendet für Tests eine Test-VM und die Azure-Verwaltung,
  nicht Deinen Mac.

## Unterschiede zu Windows

| Windows (Git Bash) | Mac |
|---|---|
| `winget install … AzureCLI` | `brew install azure-cli` |
| `export MSYS_NO_PATHCONV=1` | entfällt |
| Git Bash | Terminal mit zsh (`setopt interactive_comments` setzen) |
| `${!v}` in Prüfschleifen | in den Anleitungen ersetzt durch eine Variante, die in zsh und bash läuft |
