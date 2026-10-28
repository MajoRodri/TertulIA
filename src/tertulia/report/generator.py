import io
import logging
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .models import ReportData

log = logging.getLogger(__name__)

# ── Brand colours ─────────────────────────────────────────────────────────────
_AZUL      = HexColor("#2B4EFF")
_INK       = HexColor("#0F1730")
_MUTED     = HexColor("#7580A0")
_CANVAS    = HexColor("#F5F6FA")
_BORDER    = HexColor("#DDE1F0")
_VERDE     = HexColor("#22C55E")
_AMARILLO  = HexColor("#EAB308")
_ROJO      = HexColor("#EF4444")
_VERDE_BG  = HexColor("#DCFCE7")
_AMARILLO_BG = HexColor("#FEF9C3")
_ROJO_BG   = HexColor("#FEE2E2")

_SIGNAL_COLOR = {"green": _VERDE,     "yellow": _AMARILLO,  "red": _ROJO}
_SIGNAL_BG    = {"green": _VERDE_BG,  "yellow": _AMARILLO_BG, "red": _ROJO_BG}
_SIGNAL_LABEL = {"green": "VIABLE",   "yellow": "VIABLE CON RIESGO", "red": "NO VIABLE"}
_NARANJA      = HexColor("#7c3500")
_NARANJA_BG   = HexColor("#fde3cf")

# ── Page geometry ──────────────────────────────────────────────────────────────
_PAGE_W, _PAGE_H = A4
_ML = _MR = 2.5 * cm
_MT = 2.8 * cm
_MB = 2.5 * cm
_TW = _PAGE_W - _ML - _MR   # 16.0 cm text width

# ── Styles ─────────────────────────────────────────────────────────────────────
def _s(name, **kw) -> ParagraphStyle:
    return ParagraphStyle(name, **kw)

_STYLES = {
    "brand":    _s("brand",    fontName="Helvetica-Bold", fontSize=9,
                               textColor=_AZUL, letterSpacing=1.5, leading=12),
    "title":    _s("title",    fontName="Helvetica-Bold", fontSize=22,
                               textColor=_INK, leading=26, spaceAfter=2),
    "subtitle": _s("subtitle", fontName="Helvetica", fontSize=11,
                               textColor=_MUTED, leading=14),
    "section":  _s("section",  fontName="Helvetica-Bold", fontSize=11,
                               textColor=_INK, leading=14, spaceBefore=6),
    "label":    _s("label",    fontName="Helvetica-Bold", fontSize=8,
                               textColor=_MUTED, leading=11),
    "value":    _s("value",    fontName="Helvetica", fontSize=10,
                               textColor=_INK, leading=13),
    "agent":    _s("agent",    fontName="Helvetica-Bold", fontSize=9,
                               textColor=_INK, leading=12),
    "role":     _s("role",     fontName="Helvetica-Oblique", fontSize=8,
                               textColor=_MUTED, leading=11),
    "msg":      _s("msg",      fontName="Helvetica", fontSize=9,
                               textColor=_INK, leading=13),
    "verdict":  _s("verdict",  fontName="Helvetica-Bold", fontSize=18,
                               textColor=_INK, leading=22, alignment=TA_CENTER),
    "conf":     _s("conf",     fontName="Helvetica", fontSize=10,
                               textColor=_MUTED, leading=13, alignment=TA_CENTER),
    "reason":   _s("reason",   fontName="Helvetica", fontSize=9,
                               textColor=_INK, leading=13),
    "footer":   _s("footer",   fontName="Helvetica", fontSize=8,
                               textColor=_MUTED, leading=10, alignment=TA_CENTER),
}


# ── Page callbacks ─────────────────────────────────────────────────────────────
def _draw_header_footer(canvas, doc):
    canvas.saveState()
    # Top rule
    canvas.setStrokeColor(_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(_ML, _PAGE_H - _MT + 6*mm, _PAGE_W - _MR, _PAGE_H - _MT + 6*mm)
    # Footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_MUTED)
    canvas.drawCentredString(
        _PAGE_W / 2, _MB - 8*mm,
        f"TertulIA · Informe generado el {doc.report_date} · Ref. {doc.job_id}",
    )
    canvas.restoreState()


# ── Section builders ───────────────────────────────────────────────────────────
def _header(data: ReportData) -> list:
    brief = data.brief
    return [
        Paragraph("TERTULIA", _STYLES["brand"]),
        Spacer(1, 3*mm),
        Paragraph("Informe de Viabilidad", _STYLES["title"]),
        Paragraph(f"{brief.sector} · {brief.neighborhood}", _STYLES["subtitle"]),
        Spacer(1, 5*mm),
        HRFlowable(width="100%", thickness=0.5, color=_BORDER),
        Spacer(1, 5*mm),
    ]


def _brief_section(data: ReportData) -> list:
    brief = data.brief
    rows = [
        [Paragraph("SECTOR", _STYLES["label"]),      Paragraph(brief.sector, _STYLES["value"])],
        [Paragraph("BARRIO", _STYLES["label"]),       Paragraph(brief.neighborhood, _STYLES["value"])],
    ]
    if brief.budget_eur:
        rows.append([Paragraph("PRESUPUESTO", _STYLES["label"]),
                     Paragraph(f"{brief.budget_eur:,.0f} €", _STYLES["value"])])
    if brief.area_m2:
        rows.append([Paragraph("SUPERFICIE", _STYLES["label"]),
                     Paragraph(f"{brief.area_m2:,.0f} m²", _STYLES["value"])])
    if brief.context:
        rows.append([Paragraph("CONTEXTO", _STYLES["label"]),
                     Paragraph(brief.context, _STYLES["value"])])

    col_w = [3.2*cm, _TW - 3.2*cm]
    table = Table(rows, colWidths=col_w, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _CANVAS),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_CANVAS, white]),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4]),
        ("BOX", (0, 0), (-1, -1), 0.5, _BORDER),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, _BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    return [
        Paragraph("Ficha del encargo", _STYLES["section"]),
        Spacer(1, 3*mm),
        table,
        Spacer(1, 7*mm),
    ]


_MSG_STYLE = ParagraphStyle(
    "msg_body",
    parent=None,
    fontName="Helvetica", fontSize=9,
    textColor=_INK, leading=13,
    leftIndent=8, rightIndent=8,
    spaceBefore=2, spaceAfter=6,
)


def _debate_section(data: ReportData) -> list:
    if not data.debate:
        return []

    flowables: list = [
        Paragraph("Debate entre agentes", _STYLES["section"]),
        Spacer(1, 3*mm),
    ]

    col_w = [3.4*cm, _TW - 3.4*cm]
    for i, msg in enumerate(data.debate):
        bg = _CANVAS if i % 2 == 0 else white
        # Header row: agent name + role — always short, safe in a table
        header = Table(
            [[Paragraph(msg.name, _STYLES["agent"]), Paragraph(msg.role, _STYLES["role"])]],
            colWidths=col_w, hAlign="LEFT",
        )
        header.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), bg),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        # Message as a standalone Paragraph so ReportLab can split it across pages
        msg_style = ParagraphStyle(
            f"msg_{i}", parent=_MSG_STYLE,
            backColor=bg,
        )
        flowables.append(header)
        flowables.append(Paragraph(msg.message, msg_style))
        flowables.append(HRFlowable(width="100%", thickness=0.3, color=_BORDER))

    flowables.append(Spacer(1, 7*mm))
    return flowables


def _verdict_section(data: ReportData) -> list:
    v = data.verdict
    sig = v.signal
    color  = _SIGNAL_COLOR.get(sig, _AMARILLO)
    bg     = _SIGNAL_BG.get(sig, _AMARILLO_BG)
    label  = _SIGNAL_LABEL.get(sig, sig.upper())

    signal_style = ParagraphStyle(
        "signal_label",
        fontName="Helvetica-Bold", fontSize=13,
        textColor=color, leading=16, alignment=TA_CENTER,
    )
    verdict_summary_style = ParagraphStyle(
        "verdict_summary",
        fontName="Helvetica", fontSize=11,
        textColor=_INK, leading=15, alignment=TA_CENTER,
    )

    signal_row = Table(
        [[Paragraph(label, signal_style)]],
        colWidths=[_TW], hAlign="LEFT",
    )
    signal_row.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("BOX",           (0, 0), (-1, -1), 0.5, color),
        ("ROUNDEDCORNERS", [4]),
    ]))

    reasons = [
        Paragraph(f"• {r}", _STYLES["reason"])
        for r in (v.reasons or [])
    ]

    return [
        Paragraph("Veredicto", _STYLES["section"]),
        Spacer(1, 3*mm),
        # KeepTogether only for the signal badge + summary — short, safe to keep together
        KeepTogether([
            signal_row,
            Spacer(1, 3*mm),
            Paragraph(v.label, verdict_summary_style),
            Spacer(1, 2*mm),
            Paragraph(f"Confianza: {v.confidence}%", _STYLES["conf"]),
            Spacer(1, 5*mm),
        ]),
        # Reasons flow freely so a long list never triggers LayoutError
        *reasons,
    ]


def _simulated_notice() -> list:
    notice_style = ParagraphStyle(
        "simulated_notice",
        fontName="Helvetica-Bold", fontSize=9,
        textColor=_NARANJA, leading=12, alignment=TA_CENTER,
    )
    box = Table(
        [[Paragraph("¡Atención! DATOS DE EJEMPLO. Este informe no refleja datos reales.", notice_style)]],
        colWidths=[_TW], hAlign="LEFT",
    )
    box.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _NARANJA_BG),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 0.5, _NARANJA),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return [box, Spacer(1, 5*mm)]


_REPO_ROOT = Path(__file__).resolve().parents[3]

_AGENT_IMAGES = {
    "researcher": "portera.png",
    "analyst":    "chulapo.png",
    "vision":     "berto.png",
    "writer":     "pregonero.png",
    "reviewer":   "revisora.png",
}

_SIGNAL_LABELS = {
    "green":  "VIABLE",
    "yellow": "VIABLE CON RIESGO",
    "red":    "NO VIABLE",
}


def render_html(data: ReportData) -> str:
    import markdown as _md
    from jinja2 import Environment, FileSystemLoader
    from markupsafe import Markup, escape

    def _md_filter(text: str) -> Markup:
        return Markup(_md.markdown(str(escape(text or "")), extensions=["nl2br"]))

    _env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=True,
    )
    _env.filters["md"] = _md_filter
    assets_url = (_REPO_ROOT / "assets").as_uri() + "/"
    return _env.get_template("report.html").render(
        data=data,
        agent_images=_AGENT_IMAGES,
        signal_labels=_SIGNAL_LABELS,
        assets_url=assets_url,
    )


def _build_pdf_weasyprint(data: ReportData) -> bytes:
    from weasyprint import HTML
    html = render_html(data)
    base_url = (_REPO_ROOT / "ui").as_uri() + "/"
    return HTML(string=html, base_url=base_url).write_pdf()


def _build_pdf_reportlab(data: ReportData) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_ML, rightMargin=_MR,
        topMargin=_MT, bottomMargin=_MB,
        title=f"TertulIA · {data.brief.sector} · {data.brief.neighborhood}",
        author="TertulIA",
    )
    doc.report_date = data.generated_on.strftime("%d/%m/%Y")
    doc.job_id      = data.job_id

    frame = Frame(_ML, _MB, _TW, _PAGE_H - _MT - _MB, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=_draw_header_footer)])
    story = (
        _header(data)
        + (_simulated_notice() if data.simulated else [])
        + _brief_section(data)
        + _debate_section(data)
        + _verdict_section(data)
    )
    doc.build(story)
    return buf.getvalue()


def _build_pdf_playwright(data: ReportData) -> bytes:
    from playwright.sync_api import sync_playwright
    html = render_html(data)
    base_href = (_REPO_ROOT / "assets").as_uri() + "/"
    html = html.replace("<head>", f'<head>\n<base href="{base_href}">', 1)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        pdf = page.pdf(format="A4", print_background=True)
        browser.close()
    return pdf


# ── Public API ─────────────────────────────────────────────────────────────────
def build_pdf(data: ReportData) -> bytes:
    try:
        return _build_pdf_weasyprint(data)
    except Exception as exc:
        log.warning("WeasyPrint failed, trying Playwright: %s", exc)
    try:
        return _build_pdf_playwright(data)
    except Exception as exc:
        log.warning("Playwright failed, falling back to ReportLab: %s", exc)
    return _build_pdf_reportlab(data)
