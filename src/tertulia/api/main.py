"""TertulIA FastAPI application.

Four endpoints consumed by the UI:
  POST /api/analyze          → start a job, returns { job_id }
  GET  /api/debate/{job_id}  → SSE stream of agent messages
  GET  /api/verdict/{job_id} → Verdict (schemas model, includes final_light / final_confidence)
  POST /api/approve/{job_id} → PDF bytes
"""

import asyncio
import json
import uuid
from datetime import date, datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from tertulia.schemas.models import BusinessBrief
from tertulia.schemas.models import Verdict as SchemaVerdict
from tertulia.schemas.models import TrafficLight
from tertulia.report.models import (
    AgentMessage as ReportMessage,
    ReportBrief,
    ReportData,
    Verdict as ReportVerdict,
)

app = FastAPI(title="TertulIA API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store: { job_id: { brief, verdict, messages, status } }
_jobs: dict[str, dict] = {}

# Skeleton debate messages — replaced by real CrewAI output when agents are ready
_SKELETON_DEBATE: list[dict] = [
    {
        "agent": "researcher", "name": "Investigador", "role": "Análisis de mercado",
        "message": "He analizado 14 negocios similares en un radio de 1 km alrededor de Atocha. La densidad de cafeterías con coworking es moderada: solo 3 ofrecen tanto café de especialidad como puestos de trabajo fijos. El precio medio de alquiler en la zona es de 22 €/m².",
        "delay": 0.8,
    },
    {
        "agent": "analyst", "name": "Analista", "role": "Viabilidad financiera",
        "message": "Con 120 m² y un alquiler estimado de 2.640 €/mes, el punto de equilibrio requiere ingresar al menos 9.800 €/mes. Asumiendo un ticket medio de 8 € y una tasa de ocupación del 60%, se necesitan unos 51 clientes diarios. Es alcanzable en temporada alta, pero ajustado en agosto.",
        "delay": 1.4,
    },
    {
        "agent": "vision", "name": "Especialista Visual", "role": "Análisis de imágenes",
        "message": "He analizado 8 fotos de locales competidores en Atocha. El 75% tienen mesas pequeñas sin espacio para portátil, solo 1 muestra regletas de corriente visibles. Oportunidad de diferenciación clara en equipamiento de trabajo.",
        "delay": 1.0,
    },
    {
        "agent": "writer", "name": "Redactor", "role": "Síntesis del informe",
        "message": "El análisis muestra una oportunidad real pero con margen estrecho. La diferenciación debería centrarse en la comunidad de usuarios y en eventos temáticos que generen ingresos fuera del horario de coworking.",
        "delay": 1.8,
    },
    {
        "agent": "reviewer", "name": "Revisor", "role": "Control de calidad",
        "message": "La estimación de ocupación del 60% es optimista para el primer año; recomendaría usar 45% en el escenario base. Con ese ajuste el punto de equilibrio sube a 68 clientes diarios, viable con riesgo medio. El semáforo debería ser amarillo.",
        "delay": 2.0,
    },
    {
        "agent": "analyst", "name": "Analista", "role": "Viabilidad financiera",
        "message": "Acepto la corrección del Revisor. Con el 45% de ocupación el margen baja a 3,2%, viable pero con control estricto de costes variables. Confirmo: viabilidad media-alta, confianza 72%.",
        "delay": 1.6,
    },
]


_SKELETON_CHAT_RESPONSES = [
    {
        "agent": "analyst", "name": "Analista", "role": "Viabilidad financiera",
        "message": "Gracias por el dato adicional. He recalculado las proyecciones teniendo en cuenta lo que comentas. Actualizaré el escenario base antes del veredicto final.",
        "delay": 1.2,
    },
    {
        "agent": "reviewer", "name": "Revisor", "role": "Control de calidad",
        "message": "Incorporo el contexto en la valoración. Ajusto la confianza y los motivos del veredicto en consecuencia.",
        "delay": 1.4,
    },
]


def _skeleton_verdict() -> SchemaVerdict:
    return SchemaVerdict(
        light=TrafficLight.AMBER,
        confidence=0.72,
        summary="Viabilidad media — riesgo controlado",
        reasons=[
            "Demanda confirmada: 3 competidores directos con valoración media de 4,2 ★",
            "Punto de equilibrio alcanzable con 68 clientes/día en escenario base (45% ocupación)",
            "Riesgo estacional: agosto puede caer un 35% en afluencia",
            "Diferenciación insuficiente sin propuesta de comunidad clara",
        ],
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(brief: BusinessBrief):
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    _jobs[job_id] = {
        "brief": brief,
        "status": "running",
        "messages": [],
        "verdict": None,
        "created_at": datetime.now(timezone.utc),
    }
    return {"job_id": job_id}


@app.get("/api/debate/{job_id}")
async def debate_stream(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        _stream_debate(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_debate(job_id: str) -> AsyncGenerator[str, None]:
    messages = []
    for msg in _SKELETON_DEBATE:
        # Emit a "thinking" event before the actual message
        thinking = {"thinking": True, "agent": msg["agent"], "name": msg["name"]}
        yield f"data: {json.dumps(thinking)}\n\n"
        await asyncio.sleep(msg["delay"])
        payload = {k: v for k, v in msg.items() if k != "delay"}
        messages.append(payload)
        yield f"data: {json.dumps(payload)}\n\n"

    _jobs[job_id]["messages"] = messages
    _jobs[job_id]["verdict"] = _skeleton_verdict()
    _jobs[job_id]["status"] = "done"
    yield f"data: {json.dumps({'done': True})}\n\n"


class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat/{job_id}")
async def chat(job_id: str, req: ChatRequest):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        _stream_chat(job_id, req.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_chat(job_id: str, message: str) -> AsyncGenerator[str, None]:
    _jobs[job_id].setdefault("chat_history", []).append({"role": "user", "text": message})
    for msg in _SKELETON_CHAT_RESPONSES:
        await asyncio.sleep(msg["delay"])
        payload = {k: v for k, v in msg.items() if k != "delay"}
        yield f"data: {json.dumps(payload)}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


@app.get("/api/verdict/{job_id}")
async def get_verdict(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    verdict: SchemaVerdict = job.get("verdict") or _skeleton_verdict()
    return verdict.model_dump()


@app.post("/api/approve/{job_id}")
async def approve(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    brief: BusinessBrief = job["brief"]
    verdict: SchemaVerdict = job.get("verdict") or _skeleton_verdict()
    messages: list[dict] = job.get("messages") or [
        {k: v for k, v in m.items() if k != "delay"} for m in _SKELETON_DEBATE
    ]

    # Map amber → yellow for the PDF template (report model uses "green"/"yellow"/"red")
    signal_map = {TrafficLight.GREEN: "green", TrafficLight.AMBER: "yellow", TrafficLight.RED: "red"}
    report_signal = signal_map.get(verdict.final_light, "yellow")

    report_data = ReportData(
        job_id=job_id,
        brief=ReportBrief(
            sector=brief.business_type,
            neighborhood=brief.neighbourhood,
            budget_eur=str(int(brief.budget_eur)) if brief.budget_eur else None,
            context=brief.notes or None,
            profile=brief.user_profile.value,
        ),
        debate=[ReportMessage(**m) for m in messages],
        verdict=ReportVerdict(
            signal=report_signal,
            label=verdict.summary,
            confidence=int(verdict.final_confidence * 100),
            reasons=verdict.reasons,
        ),
        generated_on=date.today(),
    )

    try:
        from tertulia.report import build_pdf
    except ImportError:
        raise HTTPException(status_code=501, detail="weasyprint not installed — run: pip install weasyprint")

    pdf_bytes = build_pdf(report_data)
    _jobs[job_id]["status"] = "approved"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report_{job_id}.pdf"'},
    )
