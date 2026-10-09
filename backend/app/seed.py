"""Beispielinhalte: Managed Service 'Managed Virtual Infrastructure' mit vSphere- und Hyper-V-Katalog
(Basiskatalog plus Erweiterungen) und Onboarding-Vorlagen. Alles ist in der App editierbar."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import Offer, OnboardingTemplateItem, Parameter, Product, ProductExtension, User
from .security import hash_password

# (Kategorie, Name, Beschreibung, Gewicht, K.O., Empfehlung)  – Basiskatalog VMware vSphere
VSPHERE = [
    ("Lizenz & Support", "Gültiger Hersteller-Support (SnS/Subscription) für vCenter und ESXi",
     "Support-Vertrag und Lizenzschlüssel sind gültig und dem Kunden zugeordnet.", 8, True,
     "Support-Vertrag bzw. Subscription vor Vertragsstart erneuern und Support-IDs dokumentieren."),
    ("Lizenz & Support", "Lizenzedition deckt die genutzten Funktionen ab (HA, DRS, vMotion, vSAN)",
     "Keine Nutzung von Funktionen, die nicht lizenziert sind.", 6, False,
     "Lizenz-Audit durchführen und Lizenzierung an die tatsächliche Nutzung anpassen."),
    ("Versionsstand & Patching", "vCenter und ESXi laufen in einer vom Hersteller unterstützten Version",
     "Versionen sind nicht End of General Support.", 9, True,
     "Upgrade auf eine unterstützte Version planen und im Vorprojekt umsetzen."),
    ("Versionsstand & Patching", "Patchstand ist nicht älter als 6 Monate",
     "Letzte ESXi- und vCenter-Updates sind eingespielt.", 6, False,
     "Aktuellen Patchstand herstellen und einen regelmäßigen Patch-Zyklus vereinbaren."),
    ("Hardware", "Server, Storage und Controller sind auf der VMware Compatibility Guide (HCL)",
     "Prüfung inkl. Firmware- und Treiberstände.", 7, False,
     "Nicht gelistete Komponenten austauschen oder Firmware/Treiber auf HCL-Stand bringen."),
    ("Hardware", "Hardware-Support/Garantie der Hosts und Storage-Systeme läuft noch mindestens 12 Monate",
     "Gilt für Server, Storage und Netzwerkkomponenten.", 6, False,
     "Hardware-Wartung verlängern oder Austausch/Erneuerung einplanen."),
    ("Architektur & Verfügbarkeit", "HA ist aktiv und die Kapazität reicht für den Ausfall mindestens eines Hosts (N+1)",
     "Admission Control ist passend konfiguriert.", 8, False,
     "Cluster-Kapazität erweitern oder Workloads konsolidieren, sodass N+1 gewährleistet ist."),
    ("Architektur & Verfügbarkeit", "DRS ist aktiv, CPU/RAM sind nicht übermäßig überbucht",
     "Keine dauerhafte Überbuchung, die den Betrieb gefährdet.", 5, False,
     "Ressourcenplanung durchführen, Überbuchung reduzieren."),
    ("Architektur & Verfügbarkeit", "Netzwerk-Anbindung der Hosts ist redundant (mind. 2 Uplinks an getrennten Switches)",
     "Management-, vMotion- und VM-Netzwerke.", 7, False,
     "Redundante Uplinks und getrennte Switches herstellen."),
    ("Architektur & Verfügbarkeit", "Zeit- und Namensauflösung (NTP, DNS) sind korrekt, Zertifikate gültig",
     "", 4, False, "NTP/DNS korrigieren und abgelaufene Zertifikate erneuern."),
    ("Storage", "Datastore-Auslastung liegt unter 80 % und Multipathing ist redundant",
     "Gilt für klassische SAN/NAS-Datastores.", 5, False,
     "Datastores erweitern bzw. bereinigen und Pfadredundanz herstellen."),
    ("Storage", "Snapshots sind nicht älter als 72 Stunden",
     "", 4, False, "Alte Snapshots konsolidieren und Snapshot-Richtlinie festlegen."),
    ("Backup & Recovery", "Image-basierte Datensicherung (VADP) mit nachgewiesen erfolgreichem Restore-Test",
     "Letzter Restore-Test nicht älter als 12 Monate.", 9, True,
     "Backup-Lösung einführen bzw. reparieren und einen Restore-Test durchführen."),
    ("Backup & Recovery", "Backup-Ziel ist vom Produktivsystem getrennt und gegen Manipulation geschützt (offsite/immutable)",
     "", 7, False, "Zweite, getrennte oder unveränderliche Backup-Kopie einrichten."),
    ("Backup & Recovery", "RPO/RTO sind definiert und ein Notfallkonzept ist vorhanden",
     "", 5, False, "RPO/RTO mit dem Kunden abstimmen und Notfallkonzept erstellen."),
    ("Security & Zugang", "Administrativer Zugriff für den MSP ist möglich (VPN/Jump Host, eigene Admin-Konten)",
     "", 8, True, "Zugangskonzept (VPN/Jump Host, personalisierte Admin-Konten) vor Vertragsstart einrichten."),
    ("Security & Zugang", "Zentrale Authentifizierung (AD/SSO), keine geteilten root-Konten",
     "", 6, False, "vCenter an Active Directory/SSO anbinden, geteilte Konten ablösen."),
    ("Security & Zugang", "Härtung nach Herstellervorgaben (SSH aus, Lockdown-Mode, aktuelle Firewall-Regeln)",
     "", 4, False, "Härtung nach VMware Security Configuration Guide umsetzen."),
    ("Betrieb & Dokumentation", "Monitoring-Anbindung ist möglich (API/SNMP/Syslog)",
     "", 6, False, "Netzwerkfreigaben und Monitoring-Benutzer für die Anbindung einrichten."),
    ("Betrieb & Dokumentation", "Dokumentation vorhanden (Netzplan, IP-Konzept, Cluster-Design)",
     "", 5, False, "Fehlende Dokumentation im Vorprojekt erstellen (Ist-Aufnahme)."),
]

# Erweiterung VMware vSAN
VSAN = [
    ("Health & Betrieb", "vSAN-Health ist ohne Warnungen/Fehler",
     "", 8, False,
     "Offene vSAN-Health-Findings beheben, bevor der Betrieb übernommen wird."),
    ("Ausfallsicherheit", "Storage-Policies bieten Ausfalltoleranz (FTT >= 1) für alle produktiven VMs",
     "Keine VMs mit FTT=0.", 8, True, "Storage-Policies anpassen und Rebalancing/Resync einplanen."),
    ("Kapazität", "Freie vSAN-Kapazität beträgt mind. 30 % (Slack Space)",
     "", 6, False, "Kapazität erweitern oder Daten bereinigen."),
]

# (Kategorie, Name, Beschreibung, Gewicht, K.O., Empfehlung)  – Basiskatalog Microsoft Hyper-V
HYPERV = [
    ("Lizenz & Support", "Windows-Server-Lizenzen (Datacenter) decken alle Hosts ab, Software Assurance/Support vorhanden",
     "Für S2D und Azure Local gelten eigene Lizenzmodelle.", 8, True,
     "Lizenzierung bereinigen und Support-Nachweis erbringen."),
    ("Versionsstand & Patching", "Betriebssystem der Hosts ist im Herstellersupport",
     "Mainstream- oder Extended Support, kein Ablauf in den nächsten 12 Monaten.", 9, True,
     "Upgrade auf unterstützte Windows-Server-Version planen und im Vorprojekt umsetzen."),
    ("Versionsstand & Patching", "Patchstand ist nicht älter als 3 Monate",
     "", 6, False, "Aktuellen Patchstand herstellen und Patch-Zyklus vereinbaren."),
    ("Hardware", "Hardware ist im Windows Server Catalog zertifiziert bzw. als Azure-Local-Validated-Node gelistet",
     "", 8, False, "Nicht zertifizierte Komponenten austauschen oder Treiber/Firmware angleichen."),
    ("Hardware", "Hardware-Support/Garantie läuft noch mindestens 12 Monate",
     "", 6, False, "Hardware-Wartung verlängern oder Erneuerung einplanen."),
    ("Cluster", "Failover-Cluster-Validierung läuft ohne Fehler",
     "Test-Cluster-Bericht liegt vor und ist jünger als 12 Monate.", 8, True,
     "Cluster-Validierung wiederholen, Fehler beheben und Bericht dokumentieren."),
    ("Cluster", "Quorum/Witness ist konfiguriert (Cloud- oder File-Share-Witness)",
     "", 6, False, "Witness einrichten und Quorum-Konfiguration prüfen."),
    ("Cluster", "Kapazität reicht für den Ausfall mindestens eines Knotens (N+1)",
     "", 8, False, "Cluster-Kapazität erweitern oder Workloads konsolidieren."),
    ("Cluster", "Live-Migration und Netzwerke (Management, Migration, VM) sind redundant ausgelegt (SET/Teaming)",
     "", 7, False, "Netzwerkkonzept mit redundanten Uplinks umsetzen."),
    ("Backup & Recovery", "Host- oder VM-basierte Datensicherung (VSS-fähig) mit nachgewiesen erfolgreichem Restore-Test",
     "Letzter Restore-Test nicht älter als 12 Monate.", 9, True,
     "Backup-Lösung einführen bzw. reparieren und einen Restore-Test durchführen."),
    ("Backup & Recovery", "Backup-Ziel ist vom Produktivsystem getrennt und gegen Manipulation geschützt",
     "", 7, False, "Zweite, getrennte oder unveränderliche Backup-Kopie einrichten."),
    ("Backup & Recovery", "Notfallkonzept (z. B. Hyper-V Replica / Stretch Cluster) und RPO/RTO sind definiert",
     "", 5, False, "RPO/RTO mit dem Kunden abstimmen und DR-Konzept erstellen."),
    ("Security & Zugang", "Administrativer Zugriff für den MSP ist möglich (VPN/Jump Host, eigene Admin-Konten)",
     "", 8, True, "Zugangskonzept vor Vertragsstart einrichten."),
    ("Security & Zugang", "Mindestens ein Domain Controller läuft außerhalb des Clusters (physisch oder separat)",
     "Vermeidet zirkuläre Abhängigkeit beim Cluster-Start.", 6, False,
     "Domain Controller außerhalb des Clusters bereitstellen."),
    ("Security & Zugang", "Härtung der Hosts (Defender, Firewall, Admin-Tiering, Secured-Core wo möglich)",
     "", 4, False, "Härtung nach Microsoft Security Baseline umsetzen."),
    ("Betrieb & Dokumentation", "Monitoring-Anbindung ist möglich (Agent/WMI/SNMP)",
     "", 6, False, "Netzwerkfreigaben und Monitoring-Benutzer einrichten."),
    ("Betrieb & Dokumentation", "Dokumentation vorhanden (Netzplan, IP-Konzept, Cluster-Design)",
     "", 5, False, "Fehlende Dokumentation im Vorprojekt erstellen (Ist-Aufnahme)."),
]

# Erweiterung Storage Spaces Direct
S2D = [
    ("Resiliency & Health", "S2D-Volumes verwenden Mirror-Resiliency (Zweiwege oder Dreiwege-Spiegel)",
     "", 8, True,
     "Volumes mit passender Resiliency neu anlegen bzw. Cluster-Design überarbeiten."),
    ("Resiliency & Health", "Virtual Disks und Storage Pool sind 'Healthy', keine offenen Repair-Jobs",
     "", 7, False, "Defekte Laufwerke ersetzen und Repair-Jobs abwarten."),
    ("Kapazität", "Reservekapazität entspricht mind. einem Laufwerk pro Knoten (bis max. 4)",
     "", 6, False, "Kapazität erweitern oder Volumes verkleinern, um Reserve herzustellen."),
    ("Netzwerk", "RDMA (RoCE/iWARP) und DCB/PFC sind korrekt konfiguriert",
     "", 6, False, "RDMA- und DCB-Konfiguration nach Herstellervorgabe korrigieren."),
]

# Erweiterung Azure Local
AZURE_LOCAL = [
    ("Registrierung & Support", "Azure-Arc-Registrierung ist aktiv und die Abrechnung/Subscription ist gültig",
     "", 9, True,
     "Registrierung und Subscription reparieren; Verbindung zu Azure herstellen."),
    ("Updates", "Azure Local läuft auf einem unterstützten Release (nicht älter als 6 Monate)",
     "", 8, False, "Update auf aktuelle Solution-Version durchführen."),
    ("Updates", "Lifecycle-Management (Updates inkl. Solution Builder Extension) funktioniert fehlerfrei",
     "", 5, False, "Update-Pipeline prüfen und Lifecycle-Management-Fehler beheben."),
]

# (Abschnitt, Bezeichnung, Hilfe, Feldtyp, Pflicht)
ONBOARDING = [
    ("general", "Offizieller Firmenname und Rechnungsadresse", "", "textarea", True),
    ("general", "Vertragsnummer / Vertragsbeginn", "", "text", True),
    ("general", "Standorte und Rechenzentren", "Adresse, Zugangsregelung, Ansprechpartner vor Ort", "textarea", True),
    ("general", "Servicezeiten und Wartungsfenster", "", "text", True),
    ("general", "Freigabeprozess für Changes", "Wer darf Changes freigeben?", "textarea", True),
    ("general", "Geplanter Go-Live", "", "date", True),
    ("general", "Besonderheiten / Compliance-Anforderungen", "z. B. ISO 27001, KRITIS, Branchenvorgaben", "textarea", False),
    ("checklist", "Kick-off-Termin durchgeführt", "", "text", True),
    ("checklist", "Kunde und Ansprechpartner im Ticketsystem angelegt", "", "text", True),
    ("checklist", "Fernzugriff (VPN/Jump Host) eingerichtet und getestet", "", "text", True),
    ("checklist", "Monitoring angebunden, Schwellwerte abgestimmt", "", "text", True),
    ("checklist", "Backup-Überwachung aktiviert", "", "text", True),
    ("checklist", "Zugangsdaten im Passwort-Tresor hinterlegt", "", "text", True),
    ("checklist", "Dokumentation in die Betriebsdokumentation übernommen", "", "text", True),
    ("checklist", "Übergabegespräch / Service-Start bestätigt", "", "text", True),
    ("readiness", "Netzwerkplan und IP-Adresskonzept liegen vor", "", "text", True),
    ("readiness", "Administrative Zugangsdaten sicher übergeben", "", "text", True),
    ("readiness", "Lizenz- und Vertragsübersicht (Hersteller, Support-IDs) liegt vor", "", "text", True),
    ("readiness", "Hardware-Supportverträge und Hersteller-Ansprechpartner bekannt", "", "text", True),
    ("readiness", "Vollmacht gegenüber Herstellern/Lieferanten (Letter of Authorization) liegt vor", "", "text", True),
    ("readiness", "Backup-Konzept inkl. RPO/RTO und letztem Restore-Test liegt vor", "", "text", True),
    ("readiness", "Vorhandene Betriebshandbücher / Runbooks liegen vor", "", "text", False),
    ("readiness", "Eskalationsmatrix des Kunden liegt vor", "", "text", True),
    ("readiness", "Schnittstellen zu Dritten bekannt (ISP, Applikationslieferanten)", "", "text", False),
    ("readiness", "Remote-/Vor-Ort-Zugang zu allen Standorten geklärt", "", "text", True),
]


# Zusätzliche Onboarding-Punkte je Erweiterung (nur Demo-Daten): Erweiterung -> [(Abschnitt, Bezeichnung, Hilfe, Feldtyp, Pflicht)]
EXT_ONBOARDING = {
    "VMware vSAN": [
        ("readiness", "vSAN-Netzwerk (VLAN, MTU, Uplinks) ist dokumentiert", "", "text", True),
        ("readiness", "vSAN-Storage-Policies sind dokumentiert", "", "text", True),
    ],
    "Storage Spaces Direct (S2D)": [
        ("readiness", "RDMA-/DCB-Konfiguration ist dokumentiert", "", "text", True),
        ("readiness", "Volume-Layout und Resiliency sind dokumentiert", "", "text", False),
    ],
    "Azure Local": [
        ("readiness", "Azure-Subscription und Ressourcengruppe (Arc) sind bekannt", "", "text", True),
        ("readiness", "Zugriff auf das Azure-Portal für den Betrieb ist geklärt", "", "text", True),
    ],
}


def default_template_items() -> list[OnboardingTemplateItem]:
    return [OnboardingTemplateItem(section=sec, label=label, help=help_, field_type=ftype, required=req,
                                   position=(n + 1) * 10)
            for n, (sec, label, help_, ftype, req) in enumerate(ONBOARDING)]


def seed_admin(db: Session) -> None:
    if config.AUTH_LOCAL_ENABLED and not db.scalar(select(User).limit(1)):
        db.add(User(username=config.ADMIN_USER, full_name="Administrator", role="admin",
                    password_hash=hash_password(config.ADMIN_PASSWORD)))
        db.commit()


def _add_catalog(db: Session, product: Product, rows, extension=None) -> None:
    for n, (cat, name, desc, weight, blocker, rec) in enumerate(rows):
        db.add(Parameter(product_id=product.id, extension_id=extension.id if extension else None, category=cat,
                         name=name, description=desc, weight=weight, is_blocker=blocker, recommendation=rec,
                         position=(n + 1) * 10))


def _add_extension(db: Session, product: Product, name: str, description: str, position: int, rows) -> None:
    ext = ProductExtension(product_id=product.id, name=name, description=description, position=position)
    db.add(ext)
    db.flush()
    _add_catalog(db, product, rows, ext)
    for n, (section, label, help_, ftype, required) in enumerate(EXT_ONBOARDING.get(name, [])):
        db.add(OnboardingTemplateItem(product_id=product.id, extension_id=ext.id, section=section, label=label,
                                      help=help_, field_type=ftype, required=required, position=(n + 1) * 10))


def seed_demo(db: Session) -> None:
    if db.scalar(select(Offer).limit(1)):
        return
    offer = Offer(name="Managed Virtual Infrastructure",
                  description="Betrieb virtualisierter Infrastruktur auf VMware vSphere oder Microsoft Hyper-V.")
    db.add(offer)
    db.flush()
    vs = Product(offer_id=offer.id, name="VMware vSphere", description="ESXi und vCenter")
    hv = Product(offer_id=offer.id, name="Microsoft Hyper-V", description="Hyper-V-Cluster")
    for product in (vs, hv):
        product.template_items = default_template_items()
    db.add_all([vs, hv])
    db.flush()
    _add_catalog(db, vs, VSPHERE)
    _add_extension(db, vs, "VMware vSAN", "Hyperkonvergenter Storage mit vSAN", 10, VSAN)
    _add_catalog(db, hv, HYPERV)
    _add_extension(db, hv, "Storage Spaces Direct (S2D)", "Hyperkonvergenter Storage mit S2D", 10, S2D)
    _add_extension(db, hv, "Azure Local", "Azure Local (ehemals Azure Stack HCI)", 20, AZURE_LOCAL)
    db.commit()
