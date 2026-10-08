"""PDF-Report zum Service Check (ReportLab)."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from . import config

LIGHTS = {
    "green": (colors.HexColor("#2e9e4f"), "GRÜN", "Risikoarmer Betrieb durch uns als MSP ist möglich."),
    "yellow": (colors.HexColor("#e0a800"), "GELB",
               "Betrieb ist nach Behebung der genannten Befunde (Vorprojekt) risikoarm möglich."),
    "red": (colors.HexColor("#c8372d"), "ROT",
            "Betrieb in der aktuellen Form ist für uns nicht risikoarm. Ein Vorprojekt ist zwingend erforderlich."),
    "grey": (colors.HexColor("#8a8f98"), "OFFEN", "Es liegen noch keine Bewertungen vor."),
}
ANSWER_LABEL = {"yes": "Erfüllt", "partial": "Teilweise", "no": "Nicht erfüllt", "na": "Nicht anwendbar", None: "Offen"}
PRIORITY = {
    "critical": ("Kritisch – vor Vertragsstart zwingend zu beheben", colors.HexColor("#c8372d")),
    "high": ("Hoch – Bestandteil des Vorprojekts", colors.HexColor("#d9731a")),
    "medium": ("Mittel – im Vorprojekt oder zeitnah nach Übernahme", colors.HexColor("#b08900")),
    "low": ("Niedrig – im Regelbetrieb nachziehen", colors.HexColor("#5b6470")),
}
INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#5b6470")
LINE = colors.HexColor("#d5d9de")
BRAND = colors.HexColor("#1d4e89")


def _styles():
    base = getSampleStyleSheet()
    s = {
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=9.5, leading=13, textColor=INK),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=8, leading=10.5, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=8.5, leading=11, textColor=INK),
        "h1": ParagraphStyle("h1", parent=base["Title"], fontSize=21, leading=26, textColor=BRAND, alignment=0),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=13, leading=17, textColor=BRAND,
                             spaceBefore=14, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=3),
    }
    return s


def _p(text, style):
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def _light_drawing(light: str) -> Drawing:
    d = Drawing(26 * mm, 68 * mm)
    d.add(Rect(2 * mm, 2 * mm, 22 * mm, 64 * mm, rx=4 * mm, ry=4 * mm, fillColor=colors.HexColor("#2b3038"),
               strokeColor=None))
    for n, (key, y) in enumerate((("red", 53), ("yellow", 34), ("green", 15))):
        col = LIGHTS[key][0] if light == key else colors.HexColor("#4a5058")
        d.add(Circle(13 * mm, y * mm, 7 * mm, fillColor=col, strokeColor=None))
    return d


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, f"{config.REPORT_COMPANY} – Service Check – vertraulich")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Seite {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    canvas.restoreState()


def _bar(score, color) -> Drawing:
    d = Drawing(40 * mm, 4 * mm)
    d.add(Rect(0, 0.5 * mm, 40 * mm, 3 * mm, fillColor=colors.HexColor("#e6e9ed"), strokeColor=None))
    if score:
        d.add(Rect(0, 0.5 * mm, 40 * mm * score / 100, 3 * mm, fillColor=color, strokeColor=None))
    return d


def _light_for_score(score, check):
    if score is None:
        return LIGHTS["grey"][0]
    key = "red" if score < check.yellow_min else "yellow" if score < check.green_min else "green"
    return LIGHTS[key][0]


def build_report(check, result: dict) -> bytes:
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=20 * mm, title=f"Service Check – {check.title}",
                            author=config.REPORT_COMPANY)
    width = A4[0] - 36 * mm
    light = result["light"]
    color, label, verdict = LIGHTS[light]
    story = []

    # --- Kopf ---
    story += [_p(config.REPORT_COMPANY, st["small"]), Spacer(1, 2 * mm),
              _p("Service Check – Ergebnisbericht", st["h1"]), Spacer(1, 3 * mm)]
    created = check.created_at.strftime("%d.%m.%Y") if check.created_at else ""
    meta = [
        ["Kunde", check.customer.name], ["Managed Service Offer", check.offer_name], ["Produkt", check.product_name],
        ["Bezeichnung", check.title], ["Erstellt am", created],
        ["Bearbeiter", (check.created_by.full_name or check.created_by.username) if check.created_by else "–"],
        ["Status", "Abgeschlossen" if check.status == "completed" else "Entwurf (nicht abgeschlossen)"],
    ]
    meta_t = Table([[_p(k, st["small"]), _p(v, st["cell"])] for k, v in meta], colWidths=[40 * mm, None])
    meta_t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                ("TOPPADDING", (0, 0), (-1, -1), 2)]))

    # --- Ampel + Fazit ---
    score_txt = "–" if result["score"] is None else f"{result['score']:.0f} %"
    verdict_block = [
        Paragraph(f'<font color="{color.hexval().replace("0x", "#")}" size="20"><b>{label}</b></font>', st["body"]),
        Spacer(1, 2 * mm),
        _p(f"Gesamtscore: {score_txt}", st["h3"]),
        _p(verdict, st["body"]), Spacer(1, 2 * mm),
        _p(f"Schwellwerte: Grün ab {check.green_min:.0f} %, Gelb ab {check.yellow_min:.0f} %. "
           "Ein nicht erfüllter K.-o.-Parameter führt unabhängig vom Score zu Rot.", st["small"]),
    ]
    if result["blocker_failed"]:
        verdict_block += [Spacer(1, 2 * mm), _p("K.-o.-Kriterien nicht erfüllt:", st["h3"])]
        verdict_block += [_p("• " + n, st["cell"]) for n in result["blocker_failed"]]
    if not result["complete"]:
        verdict_block += [Spacer(1, 2 * mm),
                          _p(f"Hinweis: Nur {result['answered']} von {result['total']} Prüfpunkten sind bewertet – "
                             "das Ergebnis ist vorläufig.", st["small"])]
    hero = Table([[_light_drawing(light), verdict_block]], colWidths=[32 * mm, width - 32 * mm])
    hero.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                              ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f8fa")),
                              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                              ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [meta_t, Spacer(1, 6 * mm), hero]

    if check.system_description:
        story += [_p("Beschreibung des geprüften Systems", st["h2"]), _p(check.system_description, st["body"])]

    # --- Kategorien ---
    story.append(_p("Ergebnis nach Kategorien", st["h2"]))
    rows = [[_p("Kategorie", st["small"]), _p("Erfüllung", st["small"]), "", _p("Bewertet", st["small"])]]
    for c in result["categories"]:
        s = c["score"]
        rows.append([_p(c["name"], st["cell"]), _p("–" if s is None else f"{s:.0f} %", st["cell"]),
                     _bar(s, _light_for_score(s, check)), _p(f"{c['answered']}/{c['total']}", st["cell"])])
    cat_t = Table(rows, colWidths=[width - 100 * mm, 20 * mm, 45 * mm, 25 * mm], repeatRows=1)
    cat_t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(cat_t)

    # --- Empfehlungen Vorprojekt ---
    story += [PageBreak(), _p("Befunde und Empfehlungen für das Vorprojekt", st["h2"])]
    findings = result["findings"]
    if not findings:
        story.append(_p("Es wurden keine Abweichungen festgestellt. Ein Vorprojekt ist aus technischer Sicht "
                        "nicht erforderlich.", st["body"]))
    else:
        intro = {
            "green": "Es wurden nur geringfügige Abweichungen festgestellt. Sie können im Regelbetrieb abgearbeitet werden.",
            "yellow": "Wir empfehlen, die folgenden Befunde in einem Vorprojekt zu beheben, bevor der Regelbetrieb startet.",
            "red": "Wir empfehlen dringend ein Vorprojekt. Die als kritisch und hoch eingestuften Befunde müssen "
                   "vor Übernahme des Betriebs behoben werden.",
            "grey": "",
        }[light]
        story.append(_p(intro, st["body"]))
        for prio, (title, pcolor) in PRIORITY.items():
            group = [f for f in findings if f["priority"] == prio]
            if not group:
                continue
            story.append(Paragraph(f'<font color="{pcolor.hexval().replace("0x", "#")}"><b>{escape(title)}</b></font>',
                                   st["h3"]))
            rows = [[_p("Befund", st["small"]), _p("Status", st["small"]), _p("Empfohlene Maßnahme", st["small"])]]
            for f in group:
                detail = [_p(f["name"] + ("  [K.-o.]" if f["is_blocker"] else ""), st["cell"]),
                          _p(f["category"], st["small"])]
                if f["comment"]:
                    detail.append(_p("Notiz: " + f["comment"], st["small"]))
                rows.append([detail, _p(ANSWER_LABEL[f["answer"]], st["cell"]),
                             _p(f["recommendation"] or "Maßnahme im Rahmen des Vorprojekts festlegen.", st["cell"])])
            t = Table(rows, colWidths=[width * 0.38, width * 0.14, width * 0.48], repeatRows=1)
            t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f4"))]))
            story.append(t)

    # --- Anhang ---
    story += [PageBreak(), _p("Anhang: Alle Prüfpunkte", st["h2"])]
    current = None
    block = []
    for it in check.items:
        if it.category != current:
            if block:
                story.append(KeepTogether(block[:2]))
                story += block[2:]
            current = it.category
            block = [_p(current, st["h3"])]
        rows = [[_p(it.name + ("  [K.-o.]" if it.is_blocker else ""), st["cell"]),
                 _p(f"Gewicht {it.weight}", st["small"]), _p(ANSWER_LABEL[it.answer], st["cell"])]]
        if it.comment:
            rows.append([_p("Notiz: " + it.comment, st["small"]), "", ""])
        t = Table(rows, colWidths=[width * 0.62, width * 0.14, width * 0.24])
        t.setStyle(TableStyle([("LINEBELOW", (0, -1), (-1, -1), 0.3, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("SPAN", (0, 1), (-1, 1)) if it.comment else ("TOPPADDING", (0, 0), (-1, 0), 2)]))
        block.append(t)
    if block:
        story += block

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
