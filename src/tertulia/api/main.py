"""TertulIA FastAPI application.

Endpoints:
  POST /api/analyze           → start a job, returns { job_id }
  POST /api/upload/{job_id}   → upload images, returns { paths }
  GET  /api/debate/{job_id}   → SSE stream of agent messages
  POST /api/chat/{job_id}     → SSE stream of chat responses
  GET  /api/verdict/{job_id}  → Verdict JSON (includes tokens_used)
  POST /api/approve/{job_id}  → PDF bytes
"""

import asyncio
import json
import logging
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, AsyncGenerator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tertulia.graph.builder import app as _graph
from tertulia.report.models import AgentMessage as ReportMessage
from tertulia.report.models import ReportBrief, ReportData
from tertulia.report.models import Verdict as ReportVerdict
from tertulia.schemas.models import BusinessBrief, TrafficLight
from tertulia.schemas.models import Verdict as SchemaVerdict

# Project root: src/tertulia/api/main.py → 3 levels up
_ROOT = Path(__file__).resolve().parents[3]
log = logging.getLogger(__name__)

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
        "message": "He analizado 14 negocios similares en un radio de 1 km alrededor de Atocha. La densidad de cafeterías con coworking es moderada: solo 3 ofrecen tanto café de especialidad como puestos de trabajo fijos. El precio medio de alquiler en la zona es de 22 €/m².",  # noqa: E501
        "delay": 0.8,
    },
    {
        "agent": "analyst", "name": "Analista", "role": "Viabilidad financiera",
        "message": "Con 120 m² y un alquiler estimado de 2.640 €/mes, el punto de equilibrio requiere ingresar al menos 9.800 €/mes. Asumiendo un ticket medio de 8 € y una tasa de ocupación del 60%, se necesitan unos 51 clientes diarios. Es alcanzable en temporada alta, pero ajustado en agosto.",  # noqa: E501
        "delay": 1.4,
    },
    {
        "agent": "vision", "name": "Especialista Visual", "role": "Análisis de imágenes",
        "message": "He analizado 8 fotos de locales competidores en Atocha. El 75% tienen mesas pequeñas sin espacio para portátil, solo 1 muestra regletas de corriente visibles. Oportunidad de diferenciación clara en equipamiento de trabajo.",  # noqa: E501
        "delay": 1.0,
    },
    {
        "agent": "writer", "name": "Redactor", "role": "Síntesis del informe",
        "message": "El análisis muestra una oportunidad real pero con margen estrecho. La diferenciación debería centrarse en la comunidad de usuarios y en eventos temáticos que generen ingresos fuera del horario de coworking.",  # noqa: E501
        "delay": 1.8,
    },
    {
        "agent": "reviewer", "name": "Revisor", "role": "Control de calidad",
        "message": "La estimación de ocupación del 60% es optimista para el primer año; recomendaría usar 45% en el escenario base. Con ese ajuste el punto de equilibrio sube a 68 clientes diarios, viable con riesgo medio. El semáforo debería ser amarillo.",  # noqa: E501
        "delay": 2.0,
    },
    {
        "agent": "analyst", "name": "Analista", "role": "Viabilidad financiera",
        "message": "Acepto la corrección del Revisor. Con el 45% de ocupación el margen baja a 3,2%, viable pero con control estricto de costes variables. Confirmo: viabilidad media-alta, confianza 72%.",  # noqa: E501
        "delay": 1.6,
    },
]


def _skeleton_verdict() -> SchemaVerdict:
    return SchemaVerdict(
        light=TrafficLight.AMBER,
        confidence=0.72,
        summary="Viabilidad media, riesgo controlado",
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
        abs_image_paths = [
            str(_ROOT / "outputs" / p) for p in brief.image_paths
        ]
        initial_inputs = build_inputs(brief, profile, images=abs_image_paths or None)

        try:
            from tertulia.mcp.client import researcher_tools
            mcp_researcher = await asyncio.to_thread(researcher_tools)
        except Exception:
            mcp_researcher = []

        from tertulia.crew.agent_tools import default_tools as _get_tools
        _tools_map: dict = {
            "researcher": mcp_researcher,
            "analyst":    _get_tools("analyst", llm),
            "vision":     _get_tools("vision", llm),
            "writer":     [],
            "reviewer":   [],
        }

        def _run(step: str, inp: dict) -> dict:
            return run_step(step, inp, llm, _tools_map)

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
    except Exception as exc:
        log.exception("_prepare_crew failed — falling back to skeleton: %s", exc)
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
        log.warning("job=%s using skeleton debate — crew unavailable", job_id)
        yield f"data: {json.dumps({'simulated': True})}\n\n"
        for msg in _SKELETON_DEBATE:
            yield f"data: {json.dumps({'thinking': True, 'agent': msg['agent'], 'name': msg['name']})}\n\n"
            await asyncio.sleep(msg["delay"])
            payload = {k: v for k, v in msg.items() if k != "delay"}
            payload["simulated"] = True
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
                for meta in agents_meta:
                    fallback = _first_skeleton_for(meta["agent"])
                    if fallback:
                        fallback = {**fallback, "simulated": True}
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

    _jobs[job_id]["messages"]  = messages
    _jobs[job_id]["verdict"]   = _skeleton_verdict()
    _jobs[job_id]["status"]    = "paused"
    _jobs[job_id]["simulated"] = True  # always until #12 delivers a real verdict
    _jobs[job_id]["paused_at"] = datetime.now(timezone.utc)

    graph_config = {"configurable": {"thread_id": job_id}}
    graph_state = {
        "request": brief,
        "sources": [], "findings": [], "draft_report": "",
        "review_round": 0, "reviewer_comments": [],
        "verdict": _jobs[job_id]["verdict"],
        "traces": [], "tokens_used": 0,
        "human_approved": False, "expired": False, "errors": [],
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


def _build_chat_system_prompt(job: dict) -> str:
    brief: BusinessBrief = job["brief"]
    debate_lines = "\n".join(
        f"  [{m.get('name', m.get('agent', '?'))}]: {m.get('message', '')}"
        for m in (job.get("messages") or [])
    )
    history_lines = "\n".join(
        f"  {'Usuario' if h['role'] == 'user' else 'Asistente'}: {h['text']}"
        for h in (job.get("chat_history") or [])[:-1]  # exclude the current message
    )
    return (
        "Eres un equipo de consultores expertos en viabilidad de negocios. "
        "Responde en español de forma clara, directa y profesional. "
        "No repitas saludos ni preámbulos innecesarios.\n\n"
        f"CONTEXTO DEL ANÁLISIS:\n"
        f"  Tipo de negocio: {brief.business_type}\n"
        f"  Barrio: {brief.neighbourhood}\n"
        f"  Presupuesto: {brief.budget_eur} EUR\n"
        f"  Superficie: {brief.area_m2} m²\n"
        f"  Notas del usuario: {brief.notes or '(ninguna)'}\n\n"
        f"DEBATE DEL EQUIPO:\n{debate_lines or '  (sin debate previo)'}\n\n"
        + (f"CONVERSACIÓN PREVIA:\n{history_lines}\n\n" if history_lines else "")
        + "Responde a la siguiente pregunta o comentario del usuario."
    )


async def _stream_chat(job_id: str, message: str) -> AsyncGenerator[str, None]:
    job = _jobs[job_id]
    job.setdefault("chat_history", []).append({"role": "user", "text": message})

    yield f"data: {json.dumps({'thinking': True, 'agent': 'analyst', 'name': 'Analista'})}\n\n"

    response_text: str | None = None
    try:
        from tertulia.crew.crew import llm_from_settings

        llm = llm_from_settings()
        system_prompt = _build_chat_system_prompt(job)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": message},
        ]
        response_text = await asyncio.to_thread(llm.call, messages)
        # crewai LLM.call may return a string or an object with .content
        if not isinstance(response_text, str):
            response_text = getattr(response_text, "content", str(response_text))
    except Exception:
        response_text = None

    if not response_text:
        response_text = (
            "Gracias por el contexto adicional. He tenido en cuenta tu aportación "
            "y la incorporaré en la valoración final."
        )

    payload = {
        "agent": "analyst", "name": "Analista",
        "role": "Viabilidad financiera", "message": response_text,
    }
    job.setdefault("chat_history", []).append({"role": "assistant", "text": response_text})
    yield f"data: {json.dumps(payload)}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


@app.get("/api/vision/{job_id}")
async def vision_analysis(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        _stream_vision(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_vision(job_id: str) -> AsyncGenerator[str, None]:
    """Runs only the vision task with the latest image paths stored in the job."""
    brief: BusinessBrief = _jobs[job_id]["brief"]
    try:
        from tertulia.crew.agent_tools import default_tools as _get_tools
        from tertulia.crew.crew import llm_from_settings, run_step
        from tertulia.crew.inputs import build_inputs
        from tertulia.crew.sector import load_sector

        abs_image_paths = [str(_ROOT / "outputs" / p) for p in brief.image_paths]
        if not abs_image_paths:
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        llm = llm_from_settings()
        vision_tools = _get_tools("vision", llm)
        if not vision_tools:
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        profile = load_sector(brief.business_type)
        inputs = build_inputs(brief, profile, images=abs_image_paths)

        yield f"data: {json.dumps({'thinking': True, 'agent': 'vision', 'name': 'Berto'})}\n\n"

        result = await asyncio.to_thread(
            run_step, "research", inputs, llm,
            {"vision": vision_tools, "researcher": [], "analyst": [], "writer": [], "reviewer": []},
        )

        text = result.get("vision_task", "").strip()
        if text:
            payload = {
                "agent": "vision", "name": "Berto",
                "role": "Análisis de imágenes", "message": text,
            }
            _jobs[job_id].setdefault("messages", []).append(payload)
            yield f"data: {json.dumps(payload)}\n\n"

    except Exception:
        log.exception("Vision stream failed for job=%s", job_id)

    yield f"data: {json.dumps({'done': True})}\n\n"


@app.get("/api/verdict/{job_id}")
async def get_verdict(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    verdict: SchemaVerdict = job.get("verdict") or _skeleton_verdict()
    result = verdict.model_dump()
    result["tokens_used"] = job.get("tokens_used", 0)
    result["simulated"] = job.get("simulated", False)
    return result


class ApproveRequest(BaseModel):
    approved: bool = True


@app.post("/api/approve/{job_id}")
async def approve(job_id: str, req: ApproveRequest):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from config.settings import settings
    graph_config = {"configurable": {"thread_id": job_id}}

    paused_at = job.get("paused_at")
    if paused_at and (datetime.now(timezone.utc) - paused_at).total_seconds() > settings.HUMAN_TIMEOUT_S:
        await asyncio.to_thread(_graph.update_state, graph_config, {"expired": True})
        final = await asyncio.to_thread(_graph.invoke, None, graph_config)
        _jobs[job_id].update({
            "status": "expired",
            "traces": final.get("traces", []),
            "errors": final.get("errors", []),
            "sources": final.get("sources", []),
            "findings": final.get("findings", []),
            "tokens_used": final.get("tokens_used", 0),
        })
        return {"ok": False, "reason": "estudio caducado"}

    await asyncio.to_thread(_graph.update_state, graph_config, {"human_approved": req.approved})
    final = await asyncio.to_thread(_graph.invoke, None, graph_config)
    _jobs[job_id].update({
        "traces": final.get("traces", []),
        "errors": final.get("errors", []),
        "sources": final.get("sources", []),
        "findings": final.get("findings", []),
        "tokens_used": final.get("tokens_used", 0),
    })

    if not req.approved:
        _jobs[job_id]["status"] = "rejected"
        return {"ok": False, "status": "rejected"}

    brief: BusinessBrief = job["brief"]
    verdict: SchemaVerdict | None = job.get("verdict")
    if verdict is None:
        errors: list = _jobs[job_id].get("errors", [])
        reason = errors[-1].message if errors else "Presupuesto de tokens agotado sin generar veredicto"
        _jobs[job_id]["status"] = "failed"
        return {"ok": False, "reason": reason}

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
            budget_eur=brief.budget_eur,
            area_m2=brief.area_m2,
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
        simulated=job.get("simulated", False),
        tokens_used=job.get("tokens_used", 0),
    )

    try:
        from tertulia.report import build_pdf
        pdf_bytes = build_pdf(report_data)
    except (ImportError, OSError) as exc:
        raise HTTPException(status_code=501, detail=f"PDF generation unavailable: {exc}") from exc
    _jobs[job_id]["status"] = "done"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report_{job_id}.pdf"'},
    )


_ALLOWED_IMG_SUFFIXES = {".jpg", ".jpeg", ".png"}
_OUTPUTS_DIR = _ROOT / "outputs"
_MAX_IMG_BYTES = 10 * 1024 * 1024  # 10 MB


@app.post("/api/upload/{job_id}")
async def upload_images(job_id: str, files: Annotated[list[UploadFile], File()]):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    upload_dir = _OUTPUTS_DIR / job_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for f in files:
        name = Path(f.filename or "").name
        if not name or Path(name).suffix.lower() not in _ALLOWED_IMG_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"Solo se aceptan jpg y png: {f.filename!r}")
        data = await f.read()
        if len(data) > _MAX_IMG_BYTES:
            raise HTTPException(status_code=413, detail=f"{name!r} supera los 10 MB permitidos")
        dest = upload_dir / name
        dest.write_bytes(data)
        saved.append(f"{job_id}/uploads/{name}")

    brief = _jobs[job_id]["brief"]
    merged = list(brief.image_paths) + [p for p in saved if p not in brief.image_paths]
    from tertulia.schemas.models import MAX_IMAGES
    if len(merged) > MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Máximo {MAX_IMAGES} fotos por análisis")
    _jobs[job_id]["brief"] = brief.model_copy(update={"image_paths": merged})
    return {"paths": saved}


# ── Static files (must come after all API routes) ─────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse(url="/app.html")

app.mount("/assets", StaticFiles(directory=str(_ROOT / "assets")), name="assets")
app.mount("/", StaticFiles(directory=str(_ROOT / "ui")), name="ui")
