"""PDF 'Onboarding-Dokumentation' für den Kunden (ReportLab)."""
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import config
from .pdf_report import BRAND, INK, LINE, MUTED, _p, _styles, header, make_footer

SECTIONS = {
    "general": "1. Allgemeine Informationen",
    "contacts": "2. Ansprechpartner",
    "assets": "3. Installierte technische Basis",
    "checklist": "4. Onboarding-Checkliste",
    "readiness": "5. Voraussetzungen für die Serviceerbringung",
}


def _label(item) -> str:
    return item.label + (f" [{item.extension_name}]" if item.extension_name else "")
GREEN = colors.HexColor("#2e9e4f")
RED = colors.HexColor("#c8372d")


def _table(rows, widths, head=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if head else 0)
    style = [("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if head:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f4")))
    t.setStyle(TableStyle(style))
    return t


def _status(done: bool, required: bool, st):
    if done:
        return Paragraph(f'<font color="{GREEN.hexval().replace("0x", "#")}"><b>Erledigt</b></font>', st["cell"])
    col = RED if required else MUTED
    txt = "Offen" if required else "Offen (optional)"
    return Paragraph(f'<font color="{col.hexval().replace("0x", "#")}"><b>{txt}</b></font>', st["cell"])


def build_onboarding_report(ob) -> bytes:
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=20 * mm, title=f"Onboarding – {ob.customer.name}",
                            author=config.REPORT_COMPANY)
    width = A4[0] - 36 * mm
    story = [header("Onboarding-Dokumentation", st, width), Spacer(1, 5 * mm)]

    open_required = [_label(i) for i in ob.items
                     if i.required and not (i.value.strip() if i.section == "general" else i.done)]
    if not ob.contacts:
        open_required.insert(0, "Mindestens ein Ansprechpartner")
    meta = [
        ["Kunde", ob.customer.name + (f"  (KT-Nummer {ob.customer.kt_number})" if ob.customer.kt_number else "")],
        ["Managed Service", ob.offer_name], ["Produkt", ob.product_name or "\u2013"],
        ["Erweiterungen", ", ".join(e["name"] for e in ob.extensions) or "\u2013"], ["Bezeichnung", ob.title],
        ["Stand", datetime.now().strftime("%d.%m.%Y")],
        ["Status", "Abgeschlossen" if ob.status == "completed" else "In Bearbeitung"],
    ]
    t = Table([[_p(k, st["small"]), _p(v, st["cell"])] for k, v in meta], colWidths=[40 * mm, None])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (0, -1), 0)]))
    story.append(t)
    if open_required:
        story += [Spacer(1, 4 * mm), _p(f"Offene Pflichtpunkte ({len(open_required)}):", st["h3"])]
        story += [_p("• " + x, st["cell"]) for x in open_required]

    # 1. Allgemeine Informationen
    story.append(_p(SECTIONS["general"], st["h2"]))
    rows = [[_p("Angabe", st["small"]), _p("Inhalt", st["small"])]]
    for i in (x for x in ob.items if x.section == "general"):
        rows.append([_p(i.label, st["cell"]), _p(i.value or "–", st["cell"])])
    story.append(_table(rows, [width * 0.38, width * 0.62]))

    # 2. Ansprechpartner
    story.append(_p(SECTIONS["contacts"], st["h2"]))
    if ob.contacts:
        rows = [[_p(h, st["small"]) for h in ("Name / Funktion", "Telefon / Mobil", "E-Mail", "Bemerkung")]]
        for c in ob.contacts:
            rows.append([[_p(c.name, st["cell"]), _p(c.role, st["small"])],
                         [_p(c.phone, st["cell"]), _p(c.mobile, st["cell"])],
                         _p(c.email, st["cell"]), _p(c.notes, st["cell"])])
        story.append(_table(rows, [width * f for f in (0.28, 0.24, 0.26, 0.22)]))
    else:
        story.append(_p("Es wurden noch keine Ansprechpartner erfasst.", st["body"]))

    # 3. Technische Basis
    story.append(_p(SECTIONS["assets"], st["h2"]))
    if ob.assets:
        rows = [[_p(h, st["small"]) for h in ("Kategorie", "Bezeichnung / Modell", "Seriennummer", "Produkt / Version",
                                              "Anz.", "Standort", "Notiz")]]
        for a in ob.assets:
            rows.append([_p(a.category, st["cell"]), [_p(a.name, st["cell"]), _p(a.model, st["small"])],
                         _p(a.serial_number, st["cell"]), _p(a.product_version, st["cell"]),
                         _p(a.quantity, st["cell"]), _p(a.location, st["cell"]), _p(a.notes, st["cell"])])
        story.append(_table(rows, [width * f for f in (0.14, 0.2, 0.15, 0.14, 0.06, 0.12, 0.19)]))
    else:
        story.append(_p("Es wurden noch keine Systeme erfasst.", st["body"]))

    # 3./4. Checklisten
    for key in ("checklist", "readiness"):
        story.append(_p(SECTIONS[key], st["h2"]))
        rows = [[_p("Punkt", st["small"]), _p("Status", st["small"]), _p("Notiz", st["small"])]]
        for i in (x for x in ob.items if x.section == key):
            rows.append([_p(_label(i) + (" *" if i.required else ""), st["cell"]), _status(i.done, i.required, st),
                         _p(i.comment, st["cell"])])
        story.append(_table(rows, [width * 0.55, width * 0.17, width * 0.28]))
    story.append(_p("* Pflichtpunkt", st["small"]))

    # Bestätigung
    sig = Table([
        ["", ""],
        [_p(f"Datum, Unterschrift {ob.customer.name}", st["small"]), _p(f"Datum, Unterschrift {config.REPORT_COMPANY}", st["small"])],
    ], colWidths=[width / 2 - 5 * mm, width / 2 - 5 * mm], rowHeights=[18 * mm, None], hAlign="LEFT")
    sig.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.6, INK), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(KeepTogether([_p("Bestätigung der Angaben", st["h2"]),
                               _p("Die Angaben in diesem Dokument bilden die Grundlage für die Erbringung der "
                                  "vereinbarten Managed Services.", st["body"]), Spacer(1, 4 * mm), sig]))

    footer = make_footer("Onboarding-Dokumentation")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
