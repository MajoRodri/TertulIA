"""TertulIA FastAPI application.

Endpoints:
  POST /api/analyze          → start a job, returns { job_id }
  GET  /api/debate/{job_id}  → SSE stream of agent messages
  POST /api/chat/{job_id}    → SSE stream of chat responses
  GET  /api/verdict/{job_id} → Verdict JSON
  POST /api/approve/{job_id} → PDF bytes
"""

import asyncio
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Project root: src/tertulia/api/main.py → 3 levels up
_ROOT = Path(__file__).resolve().parents[3]

from tertulia.graph.builder import app as _graph
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

# ── Crew step metadata ────────────────────────────────────────────────────────
# Each entry: (crew_step_name, list of agent display info + task output key)
_STEP_META: list[tuple[str, list[dict]]] = [
    ("research", [
        {"agent": "researcher", "name": "Investigador",        "role": "Análisis de mercado",  "task": "research_task"},
        {"agent": "vision",     "name": "Especialista Visual", "role": "Análisis de imágenes", "task": "vision_task"},
    ]),
    ("analysis", [
        {"agent": "analyst",  "name": "Analista", "role": "Viabilidad financiera", "task": "analysis_task"},
    ]),
    ("writing", [
        {"agent": "writer",   "name": "Redactor", "role": "Síntesis del informe",  "task": "writing_task"},
    ]),
    ("review", [
        {"agent": "reviewer", "name": "Revisor",  "role": "Control de calidad",    "task": "review_task"},
    ]),
]

# ── Skeleton data (demo / fallback) ──────────────────────────────────────────

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


def _first_skeleton_for(agent: str) -> dict | None:
    """First skeleton message matching the given agent id."""
    for msg in _SKELETON_DEBATE:
        if msg["agent"] == agent:
            return {k: v for k, v in msg.items() if k != "delay"}
    return None


# ── Crew helpers ──────────────────────────────────────────────────────────────

async def _prepare_crew(brief: BusinessBrief):
    """
    Loads sector profile, builds LLM, and returns closures for the debate loop.
    Returns None when any dependency is missing (no API key, unknown sector, etc.).
    """
    try:
        from tertulia.crew.crew import llm_from_settings, run_step
        from tertulia.crew.inputs import build_inputs
        from tertulia.crew.sector import load_sector

        profile = load_sector(brief.business_type)
        llm = llm_from_settings()
        initial_inputs = build_inputs(brief, profile)

        def _run(step: str, inp: dict) -> dict:
            return run_step(step, inp, llm)

        def _rebuild(acc: dict) -> dict:
            return build_inputs(
                brief,
                profile,
                research_result=acc.get("research_result"),
                vision_result=acc.get("vision_result"),
                analysis_result=acc.get("analysis_result"),
                draft_report=acc.get("draft_report"),
            )

        return _run, _rebuild, initial_inputs
    except Exception:
        return None


def _accumulate(step: str, result: dict[str, str], acc: dict) -> None:
    """Stores step outputs so later steps can reference them via build_inputs."""
    if step == "research":
        acc["research_result"] = result.get("research_task", "")
        acc["vision_result"]   = result.get("vision_task", "")
    elif step == "analysis":
        acc["analysis_result"] = result.get("analysis_task", "")
    elif step == "writing":
        acc["draft_report"]    = result.get("writing_task", "")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(brief: BusinessBrief):
    from tertulia.guardrails.anonimizacion import anonymize_business_brief
    brief = anonymize_business_brief(brief)
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
    brief: BusinessBrief = _jobs[job_id]["brief"]
    messages: list[dict] = []

    crew = await _prepare_crew(brief)

    if crew is None:
        # Skeleton demo — no LLM calls
        for msg in _SKELETON_DEBATE:
            yield f"data: {json.dumps({'thinking': True, 'agent': msg['agent'], 'name': msg['name']})}\n\n"
            await asyncio.sleep(msg["delay"])
            payload = {k: v for k, v in msg.items() if k != "delay"}
            messages.append(payload)
            yield f"data: {json.dumps(payload)}\n\n"
    else:
        run_step_fn, rebuild_inputs, inputs = crew
        accumulated: dict = {}

        for step_name, agents_meta in _STEP_META:
            first = agents_meta[0]
            yield f"data: {json.dumps({'thinking': True, 'agent': first['agent'], 'name': first['name']})}\n\n"

            try:
                result: dict[str, str] = await asyncio.to_thread(run_step_fn, step_name, inputs)
            except Exception:
                # Per-step fallback so the UI never stalls
                for meta in agents_meta:
                    fallback = _first_skeleton_for(meta["agent"])
                    if fallback:
                        messages.append(fallback)
                        yield f"data: {json.dumps(fallback)}\n\n"
                continue

            _accumulate(step_name, result, accumulated)
            inputs = rebuild_inputs(accumulated)

            for meta in agents_meta:
                text = result.get(meta["task"], "").strip()
                if not text:
                    continue
                payload = {
                    "agent": meta["agent"],
                    "name":  meta["name"],
                    "role":  meta["role"],
                    "message": text,
                }
                messages.append(payload)
                yield f"data: {json.dumps(payload)}\n\n"

    _jobs[job_id]["messages"] = messages
    _jobs[job_id]["verdict"]  = _skeleton_verdict()
    _jobs[job_id]["status"]   = "paused"

    graph_config = {"configurable": {"thread_id": job_id}}
    graph_state = {
        "request": brief,
        "sources": [], "findings": [], "draft_report": "",
        "review_round": 0, "reviewer_comments": [],
        "verdict": _jobs[job_id]["verdict"],
        "traces": [], "tokens_used": 0,
        "human_approved": False, "errors": [],
    }
    await asyncio.to_thread(_graph.invoke, graph_state, graph_config)
    yield f"data: {json.dumps({'paused': True})}\n\n"


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


class ApproveRequest(BaseModel):
    approved: bool = True


@app.post("/api/approve/{job_id}")
async def approve(job_id: str, req: ApproveRequest | None = None):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    approved = req.approved if req is not None else True
    graph_config = {"configurable": {"thread_id": job_id}}

    await asyncio.to_thread(_graph.update_state, graph_config, {"human_approved": approved})
    final = await asyncio.to_thread(_graph.invoke, None, graph_config)
    _jobs[job_id]["traces"] = final.get("traces", [])

    if not approved:
        _jobs[job_id]["status"] = "rejected"
        return {"ok": False, "status": "rejected"}

    brief: BusinessBrief = job["brief"]
    verdict: SchemaVerdict = job.get("verdict") or _skeleton_verdict()
    messages: list[dict] = job.get("messages") or [
        {k: v for k, v in m.items() if k != "delay"} for m in _SKELETON_DEBATE
    ]

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


# ── Static files (must come after all API routes) ─────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse(url="/app.html")

app.mount("/assets", StaticFiles(directory=str(_ROOT / "assets")), name="assets")
app.mount("/", StaticFiles(directory=str(_ROOT / "ui")), name="ui")
