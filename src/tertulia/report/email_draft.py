from .models import ReportData

_SIGNAL_LABELS = {
    "green":  "✅ Alta viabilidad",
    "yellow": "⚠️  Datos insuficientes o riesgo",
    "red":    "🔴 Baja viabilidad",
}


def build_email_draft(data: ReportData) -> str:
    signal_text = _SIGNAL_LABELS.get(data.verdict.signal, data.verdict.signal)
    reasons = "\n".join(f"  • {r}" for r in data.verdict.reasons)

    return f"""\
Asunto: Informe de viabilidad — {data.brief.sector} en {data.brief.neighborhood} (Ref. {data.job_id})

Estimado/a cliente,

Le enviamos el informe de viabilidad generado por TertulIA para el encargo recibido.

─────────────────────────────────────────
RESUMEN DEL ENCARGO
─────────────────────────────────────────
Sector:        {data.brief.sector}
Zona:          {data.brief.neighborhood}
Presupuesto:   {data.brief.budget_eur or '—'} €
Superficie:    {data.brief.area_m2 or '—'} m²

─────────────────────────────────────────
VEREDICTO
─────────────────────────────────────────
{signal_text}
Confianza: {data.verdict.confidence}%

Motivos principales:
{reasons}

─────────────────────────────────────────

Encontrará el informe completo en PDF adjunto a este correo.

Este análisis es orientativo. Le recomendamos verificar las fuentes y \
contrastar las cifras con un profesional antes de tomar decisiones de inversión.

Un saludo,
Equipo TertulIA
"""
