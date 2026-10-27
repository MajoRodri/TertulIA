from tertulia.report import (
    AgentMessage,
    ReportBrief,
    ReportData,
    Verdict,
    build_email_draft,
    render_html,
)

SAMPLE_DATA = ReportData(
    job_id="test-001",
    brief=ReportBrief(sector="café-cowork", neighborhood="Atocha", budget_eur=80000.0, area_m2=120.0),
    debate=[
        AgentMessage(
            agent="researcher", name="Investigador",
            role="Análisis de mercado", message="Hay 14 negocios similares.",
        ),
        AgentMessage(
            agent="analyst", name="Analista",
            role="Viabilidad financiera", message="Punto de equilibrio: 68 clientes/día.",
        ),
    ],
    verdict=Verdict(
        signal="yellow", label="Viabilidad media",
        confidence=72, reasons=["Riesgo estacional en agosto"],
    ),
)


def test_render_html_contains_key_data():
    html = render_html(SAMPLE_DATA)
    assert "Atocha" in html
    assert "Investigador" in html
    assert "Viabilidad media" in html
    assert "72" in html


def test_render_html_traffic_light_class():
    html = render_html(SAMPLE_DATA)
    assert "active yellow" in html
    assert "active green" not in html
    assert "active red" not in html


def test_email_draft_contains_summary():
    draft = build_email_draft(SAMPLE_DATA)
    assert "Atocha" in draft
    assert "72%" in draft
    assert "Riesgo estacional" in draft
    assert "test-001" in draft


def test_email_draft_signal_label():
    draft = build_email_draft(SAMPLE_DATA)
    assert "Viabilidad media" in draft
