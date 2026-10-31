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
import base64
import io
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, AsyncGenerator

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import settings
from tertulia.graph.builder import app as _graph
from tertulia.report.models import AgentMessage as ReportMessage
from tertulia.report.models import ReportBrief, ReportData, ReportFinding, ReportSource
from tertulia.report.models import Verdict as ReportVerdict
from tertulia.schemas.models import BusinessBrief, TrafficLight
from tertulia.schemas.models import Verdict as SchemaVerdict
from tertulia.trazas import save_traces

# Project root: src/tertulia/api/main.py → 3 levels up
_ROOT = Path(__file__).resolve().parents[3]
log = logging.getLogger(__name__)

# MCP tools loaded once at startup and reused across debates (~9 s saved per debate).
# Each tool call still opens its own connection via _patient_client; only the schema
# discovery (resolver.resolve) is cached here.
_mcp_researcher_tools: list = []


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _mcp_researcher_tools
    try:
        from tertulia.mcp.client import researcher_tools
        _mcp_researcher_tools = await asyncio.to_thread(researcher_tools)
        log.info("MCP tools ready at startup (%d tools)", len(_mcp_researcher_tools))
    except Exception:
        log.warning("MCP tools unavailable at startup — debates will run without them", exc_info=True)
        _mcp_researcher_tools = []
    yield


app = FastAPI(title="TertulIA API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://esm.sh; "
    "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self' https://esm.sh; "
    "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
    "worker-src blob:; "
    "frame-ancestors 'none'"
)


@app.middleware("http")
async def _csp_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# In-memory store: { job_id: { brief, verdict, messages, status } }
_jobs: dict[str, dict] = {}

# Serializes scoped_handlers() calls — crewai event bus is process-global
_research_lock = threading.Lock()

# Rate limiting buckets: { (ip, key): [timestamp, ...] }
_rate_buckets: dict = defaultdict(list)
_rate_call_count = 0


def _check_rate_limit(ip: str, key: str, max_calls: int, window_s: int = 60) -> None:
    """Raise HTTP 429 if ip has exceeded max_calls within the sliding window."""
    global _rate_call_count
    bucket_key = (ip, key)
    now = time.monotonic()
    _rate_buckets[bucket_key] = [t for t in _rate_buckets[bucket_key] if now - t < window_s]
    if len(_rate_buckets[bucket_key]) >= max_calls:
        raise HTTPException(status_code=429, detail="Demasiadas peticiones. Espera un momento.")
    _rate_buckets[bucket_key].append(now)
    _rate_call_count += 1
    if _rate_call_count % 1000 == 0:
        stale = [k for k, v in _rate_buckets.items() if not v or now - max(v) > window_s]
        for k in stale:
            del _rate_buckets[k]

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


def _verdict_from_draft(
    draft: str,
    findings: list,
    sources: list,
) -> SchemaVerdict:
    """Parse the writer's Markdown draft to build a real Verdict.

    The writing task always ends with a semáforo section that contains the
    traffic light color and bullet-point reasons. If parsing fails for any
    field, safe fallbacks are used so the verdict is never None.
    """
    import re

    from tertulia.schemas.models import compute_confidence

    confidence = compute_confidence(findings, sources)

    # Locate the semáforo / veredicto section (last ## heading that matches).
    semaforo_block = ""
    match = re.search(
        r"#{1,3}[^#\n]*[Ss]em[aá]foro[^#\n]*\n(.*?)(?=\n#{1,3}|\Z)",
        draft,
        re.DOTALL,
    )
    if match:
        semaforo_block = match.group(1)

    # Determine traffic light from color keywords — case-insensitive so ROJO/rojo/Rojo all match.
    # Search only inside the semáforo block to avoid false positives from phrases like
    # "números rojos" or "zona verde" in the analysis body.
    search_in = semaforo_block or draft
    if re.search(r"\bverde\b", search_in, re.IGNORECASE):
        light = TrafficLight.GREEN
    elif re.search(r"\brojo\b", search_in, re.IGNORECASE):
        light = TrafficLight.RED
    else:
        light = TrafficLight.AMBER

    # Extract bullet-point reasons: accept -, *, + and numbered lists (1. 2. etc.)
    reasons: list[str] = [
        m.group(1).strip()
        for m in re.finditer(r"^(?:[-*+]|\d+\.)\s+(.+)", semaforo_block, re.MULTILINE)
    ]
    if not reasons:
        # Fall back: any non-empty, non-heading line in the semáforo block
        reasons = [
            line.strip()
            for line in semaforo_block.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ] or ["Ver informe completo para los motivos del semáforo."]

    # Build summary: first non-bullet, non-heading, non-empty line in the semáforo block.
    summary = ""
    for line in semaforo_block.splitlines():
        line = line.strip()
        if line and not line.startswith(("-", "*", "+", "#")) and not re.match(r"^\d+\.", line):
            summary = line
            break
    if not summary:
        resumen = re.search(r"#{1,3}[^#\n]*[Rr]esumen[^#\n]*\n(.+)", draft)
        summary = resumen.group(1).strip() if resumen else "Análisis de viabilidad completado."

    return SchemaVerdict(
        light=light,
        confidence=confidence,
        summary=summary,
        reasons=reasons,
    )


async def _compute_and_cache_verdict(job_id: str) -> None:
    """Compute the real verdict and cache it in _jobs.

    Called lazily from GET /api/verdict when the user reaches step 4.
    At that point the chat_history from step 3 is already available, so we
    can run the writer with chat_context to get a context-informed verdict.

    If no chat_context exists we extract the verdict from the debate draft.
    If the crew call fails we fall back to the debate draft silently.
    """
    job = _jobs[job_id]

    chat_history = job.get("chat_history", [])
    doc_context  = job.get("doc_context", "")
    context_parts: list[str] = []
    if doc_context:
        context_parts.append(f"DOCUMENTOS APORTADOS POR EL USUARIO:\n{doc_context}")
    if chat_history:
        history_text = "\n".join(
            f"Usuario: {h['text']}" if h["role"] == "user" else f"Asistente: {h['text']}"
            for h in chat_history
        )
        context_parts.append(f"CONVERSACIÓN DE CONTEXTO:\n{history_text}")

    from tertulia.guardrails.anonimizacion import _scrub
    chat_context = _scrub("\n\n".join(context_parts)) if context_parts else ""

    draft    = job.get("draft_report", "")
    findings = job.get("mcp_findings", [])
    sources  = job.get("mcp_sources", [])

    if chat_context and draft:
        try:
            from tertulia.crew.crew import llm_from_settings, run_step
            from tertulia.crew.inputs import build_inputs
            from tertulia.crew.sector import load_sector

            brief: BusinessBrief = job["brief"]
            profile = load_sector(brief.business_type)
            inputs = build_inputs(
                brief, profile,
                research_result=job.get("research_result"),
                vision_result=job.get("vision_result"),
                analysis_result=job.get("analysis_result"),
                draft_report=draft,
                chat_context=chat_context,
                mcp_research_summary="\n".join(job.get("mcp_research_summary", [])),
            )
            result = await asyncio.to_thread(run_step, "writing", inputs, llm_from_settings())
            draft = result.get("writing_task") or draft
            _jobs[job_id]["draft_report"]           = draft
            _jobs[job_id]["chat_context_precomputed"] = True
        except Exception:
            log.warning("writer rerun for verdict failed job=%s, falling back to debate draft", job_id, exc_info=True)

    try:
        verdict = _verdict_from_draft(draft, findings, sources)
        _jobs[job_id]["verdict"]   = verdict
        _jobs[job_id]["simulated"] = False
    except Exception:
        log.warning("verdict extraction failed job=%s, keeping skeleton", job_id, exc_info=True)

    _jobs[job_id]["verdict_ready"] = True


def _first_skeleton_for(agent: str) -> dict | None:
    """First skeleton message matching the given agent id."""
    for msg in _SKELETON_DEBATE:
        if msg["agent"] == agent:
            return {k: v for k, v in msg.items() if k != "delay"}
    return None


# ── Demo job (pre-seeded for USE_MOCK=true frontend mode) ────────────────────
_jobs["demo-001"] = {
    "brief": BusinessBrief(
        business_type="cafe_cowork",
        neighbourhood="Atocha",
        budget_eur=80_000,
        area_m2=120,
        radius_m=800,
    ),
    "verdict": _skeleton_verdict(),
    "messages": [{k: v for k, v in m.items() if k != "delay"} for m in _SKELETON_DEBATE],
    "status": "paused",
    "paused_at": None,  # skip timeout check for demo
    "debate_simulated": True,
    "simulated": True,
    "is_demo": True,
    "tokens_used": 0,
    "sources": [],
    "findings": [],
    "traces": [],
    "errors": [],
}

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
        initial_inputs = build_inputs(brief, profile, images=brief.image_paths or None)

        mcp_researcher = _mcp_researcher_tools

        from tertulia.crew.agent_tools import default_tools as _get_tools
        _tools_map: dict = {
            "researcher": mcp_researcher,
            "analyst":    _get_tools("analyst", llm),
            "vision":     _get_tools("vision", llm),
            "writer":     [],
            "reviewer":   [],
        }

        _tracking: dict = {"foursquare_used": False}

        def _run(step: str, inp: dict) -> dict:
            usage_before = getattr(llm, "token_usage", {}).get("total_tokens", 0)
            if step != "research":
                result = run_step(step, inp, llm, _tools_map)
            else:
                # For the research step, listen for Foursquare usage via MCP events.
                # Import errors mean tracking is unavailable — run without it.
                try:
                    import json as _json

                    from crewai.events import crewai_event_bus
                    from crewai.events.types.mcp_events import MCPToolExecutionCompletedEvent
                except Exception:
                    result = run_step(step, inp, llm, _tools_map)
                else:
                    detected = [False]

                    def _check(source, event):
                        if event.tool_name != "search_competitors":
                            return
                        try:
                            r = _json.loads(event.result) if isinstance(event.result, str) else event.result
                            if not isinstance(r, dict):
                                return
                            if r.get("foursquare_status") == "used":
                                detected[0] = True
                            from tertulia.tools.adapters import mcp_response_to_sources_and_findings
                            start_src = 1 + len(_tracking.get("mcp_sources", []))
                            start_fnd = 1 + len(_tracking.get("mcp_findings", []))
                            srcs, fnds, summary = mcp_response_to_sources_and_findings(
                                r,
                                start_source_index=start_src,
                                start_finding_index=start_fnd,
                            )
                            _tracking.setdefault("mcp_sources", []).extend(srcs)
                            _tracking.setdefault("mcp_findings", []).extend(fnds)
                            _tracking.setdefault("mcp_research_summary", []).append(summary)
                        except Exception:
                            pass

                    # _research_lock serializes scoped_handlers() across concurrent requests —
                    # crewai event bus is process-global and would cross-contaminate listeners.
                    with _research_lock, crewai_event_bus.scoped_handlers():
                        crewai_event_bus.on(MCPToolExecutionCompletedEvent)(_check)
                        result = run_step(step, inp, llm, _tools_map)
                    if detected[0]:
                        _tracking["foursquare_used"] = True
            usage_after = getattr(llm, "token_usage", {}).get("total_tokens", 0)
            _tracking["tokens_used"] = _tracking.get("tokens_used", 0) + max(0, usage_after - usage_before)
            return result

        def _rebuild(acc: dict) -> dict:
            return build_inputs(
                brief,
                profile,
                research_result=acc.get("research_result"),
                vision_result=acc.get("vision_result"),
                analysis_result=acc.get("analysis_result"),
                draft_report=acc.get("draft_report"),
                mcp_research_summary="\n".join(_tracking.get("mcp_research_summary", [])),
            )

        return _run, _rebuild, initial_inputs, _tracking
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
    elif step == "review":
        acc["review_result"]   = result.get("review_task", "")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(brief: BusinessBrief, request: Request):
    _check_rate_limit(request.client.host, "analyze", settings.RATE_LIMIT_ANALYZE)
    from tertulia.guardrails.anonimizacion import anonymize_business_brief
    brief = anonymize_business_brief(brief)
    job_id = f"job-{uuid.uuid4().hex}"
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

    debate_simulated = crew is None

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
        run_step_fn, rebuild_inputs, inputs, _tracking = crew
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
            if step_name == "research":
                summaries = _tracking.get("mcp_research_summary", [])
                if summaries:
                    existing = accumulated.get("research_result", "")
                    accumulated["research_result"] = (
                        existing + "\n\n" + "\n\n".join(summaries)
                    ).strip()
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

        _jobs[job_id]["research_result"] = accumulated.get("research_result", "")
        _jobs[job_id]["vision_result"]   = accumulated.get("vision_result", "")
        _jobs[job_id]["analysis_result"] = accumulated.get("analysis_result", "")
        _jobs[job_id]["draft_report"]    = accumulated.get("draft_report", "")

    _jobs[job_id]["messages"]          = messages
    _jobs[job_id]["status"]            = "paused"
    _jobs[job_id]["debate_simulated"]  = debate_simulated
    _jobs[job_id]["verdict"]           = _skeleton_verdict()
    _jobs[job_id]["simulated"]         = debate_simulated
    _jobs[job_id]["verdict_ready"]     = False
    _jobs[job_id]["paused_at"]         = datetime.now(timezone.utc)
    _jobs[job_id]["foursquare_used"]      = _tracking.get("foursquare_used", False) if crew else False
    _jobs[job_id]["mcp_sources"]          = _tracking.get("mcp_sources", []) if crew else []
    _jobs[job_id]["mcp_findings"]         = _tracking.get("mcp_findings", []) if crew else []
    _jobs[job_id]["mcp_research_summary"] = _tracking.get("mcp_research_summary", []) if crew else []

    graph_config = {"configurable": {"thread_id": job_id}}
    graph_state = {
        "request": brief,
        "sources":  _jobs[job_id].get("mcp_sources", []),
        "findings": _jobs[job_id].get("mcp_findings", []),
        "draft_report":         _jobs[job_id].get("draft_report", ""),
        "research_result":      _jobs[job_id].get("research_result", ""),
        "vision_result":        _jobs[job_id].get("vision_result", ""),
        "analysis_result":      _jobs[job_id].get("analysis_result", ""),
        "mcp_research_summary": "\n".join(_jobs[job_id].get("mcp_research_summary", [])),
        "review_round": 0, "reviewer_comments": [],
        "verdict": _jobs[job_id]["verdict"],
        "traces": [], "tokens_used": _tracking.get("tokens_used", 0) if crew else 0,
        "human_approved": False, "expired": False, "errors": [],
        "chat_context": "", "chat_context_applied": False,
        "discarded_competitors": [],
    }
    await asyncio.to_thread(_graph.invoke, graph_state, graph_config)
    yield f"data: {json.dumps({'paused': True})}\n\n"


def _sanitize_chat_image(mime: str, data: bytes) -> tuple[str, bytes]:
    from PIL import Image, ImageOps  # type: ignore[import-untyped]
    _ALLOWED = {"JPEG": "image/jpeg", "PNG": "image/png"}
    try:
        buf = io.BytesIO(data)
        with Image.open(buf) as img:
            fmt = img.format
            img.verify()
        if fmt not in _ALLOWED:
            raise ValueError(f"unsupported format: {fmt}")
        buf.seek(0)
        with Image.open(buf) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((1600, 1600), Image.LANCZOS)
            if fmt == "JPEG" and img.mode != "RGB":
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format=fmt)
        return _ALLOWED[fmt], out.getvalue()
    except Exception as exc:
        raise ValueError("invalid image") from exc


# ── Document upload helpers ────────────────────────────────────
MAX_DOC_MB    = 5
MAX_DOC_BYTES = MAX_DOC_MB * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_DOC_CHARS = 50_000

_DOC_TYPE_LABELS: dict[str, str] = {
    "plan_negocio":          "Plan de negocio",
    "proyeccion_financiera": "Proyección financiera",
    "estudio_mercado":       "Estudio de mercado",
    "contrato":              "Contrato / local",
    "presupuesto":           "Presupuesto de obra",
    "otro":                  "Otro documento",
}


def _extract_document_text(filename: str, mime: str, data: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("md", "txt") or mime in ("text/markdown", "text/plain"):
        return data.decode("utf-8", errors="replace")[:MAX_DOC_CHARS]
    if ext == "pdf" or mime == "application/pdf":
        from pypdf import PdfReader  # type: ignore[import-untyped]
        try:
            reader = PdfReader(io.BytesIO(data))
            n_pages = len(reader.pages)
            if n_pages > MAX_PDF_PAGES:
                raise ValueError(f"el PDF tiene {n_pages} páginas (máximo {MAX_PDF_PAGES})")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"el PDF no se puede leer (puede estar cifrado o dañado): {exc}") from exc
        if not text.strip():
            raise ValueError("el PDF no contiene texto extraíble (puede ser un PDF escaneado)")
        return text[:MAX_DOC_CHARS]
    raise ValueError(f"formato no soportado: {ext or mime}")


def _classify_document(llm, text: str, declared_type: str, brief) -> tuple[bool, str]:
    """Returns (is_valid, category_or_rejection_reason)."""
    label = _DOC_TYPE_LABELS.get(declared_type, declared_type)
    prompt = (
        f"Clasifica si el siguiente documento es relevante para un análisis de viabilidad "
        f"de un negocio de tipo '{brief.business_type}' en {brief.neighbourhood}.\n"
        f"El usuario lo ha declarado como: {label}.\n\n"
        f"FRAGMENTO DEL DOCUMENTO:\n{text[:1500]}\n\n"
        "Responde EXACTAMENTE con una sola línea:\n"
        "VÁLIDO: <categoría breve>   — si es relevante para el análisis de negocio\n"
        "INVÁLIDO: <motivo breve>    — si no tiene relación con el negocio analizado"
    )
    messages = [
        {"role": "system", "content": (
            "Eres un clasificador de documentos. Responde solo con VÁLIDO o INVÁLIDO "
            "seguido de dos puntos y una descripción breve en español."
        )},
        {"role": "user", "content": prompt},
    ]
    try:
        response = llm.call(messages)
        if not isinstance(response, str):
            response = getattr(response, "content", str(response))
        response = response.strip()
        upper = response.upper()
        if upper.startswith("VÁLIDO") or upper.startswith("VALIDO"):
            category = response.split(":", 1)[-1].strip() if ":" in response else label
            return True, category
        reason = response.split(":", 1)[-1].strip() if ":" in response else response
        return False, reason
    except Exception:
        log.warning("Document classification failed — rejecting for safety", exc_info=True)
        return False, "No se pudo verificar la relevancia del documento"


MAX_DOC_CONTEXT_CHARS = 50_000  # total cap across all uploaded documents


def _guard_document(text: str, source: str) -> tuple[bool, list[str], str]:
    """Runs the injection guard over the full text, processing in MAX_CHARS chunks.

    process() truncates to MAX_CHARS (8 k); documents can be much larger.
    Returns (suspicious, patterns, wrapped_text).
    """
    from tertulia.guardrails.injection import MAX_CHARS
    from tertulia.guardrails.injection import process as guard_process

    if not text:
        return False, [], ""
    suspicious = False
    patterns: list[str] = []
    parts: list[str] = []
    for i in range(0, len(text), MAX_CHARS):
        result = guard_process(text[i: i + MAX_CHARS], source=source)
        if result.suspicious:
            suspicious = True
            for p in result.patterns:
                if p not in patterns:
                    patterns.append(p)
        parts.append(result.wrapped_text)
    return suspicious, patterns, "\n".join(parts)


async def _process_documents(
    uploads: list[UploadFile],
    doc_types: list[str] | None,
    brief,
    llm,
) -> tuple[str, list[str]]:
    """Extracts, validates, and classifies uploaded documents.

    Returns (combined_text, rejection_messages).
    """
    from tertulia.guardrails.anonimizacion import _scrub

    accepted: list[str] = []
    rejected: list[str] = []
    total_chars = 0

    for i, upload in enumerate(uploads):
        declared_type = (doc_types or [])[i] if doc_types and i < len(doc_types) else "otro"
        raw = await upload.read()

        if len(raw) > MAX_DOC_BYTES:
            rejected.append(f'"{upload.filename}" supera los {MAX_DOC_MB} MB permitidos')
            continue

        try:
            text = await asyncio.to_thread(
                _extract_document_text,
                upload.filename or "",
                upload.content_type or "",
                raw,
            )
        except ValueError as exc:
            rejected.append(f'"{upload.filename}": {exc}')
            continue

        # Injection guard: process full text in chunks, then anonymize
        suspicious, _patterns, wrapped = _guard_document(text, source=f"documento:{upload.filename}")
        if suspicious:
            log.warning("Suspicious content in document %s: %s", upload.filename, _patterns)
            rejected.append(
                f'"{upload.filename}" contiene instrucciones sospechosas y no se ha incluido'
            )
            continue
        text = _scrub(wrapped)

        is_valid, category_or_reason = await asyncio.to_thread(
            _classify_document, llm, text, declared_type, brief
        )
        if not is_valid:
            rejected.append(
                f'"{upload.filename}" no parece relevante para este análisis: {category_or_reason}'
            )
            continue

        if total_chars >= MAX_DOC_CONTEXT_CHARS:
            rejected.append(
                f'"{upload.filename}" no se incluyó: se alcanzó el límite total de contexto '
                f"({MAX_DOC_CONTEXT_CHARS // 1000} k caracteres)"
            )
            continue

        label = _DOC_TYPE_LABELS.get(declared_type, declared_type)
        entry = f"[{label} — {upload.filename}]\n{text}"
        remaining = MAX_DOC_CONTEXT_CHARS - total_chars
        accepted.append(entry[:remaining])
        total_chars += min(len(entry), remaining)

    combined = "\n\n---\n\n".join(accepted)
    return combined, rejected


@app.post("/api/documents/{job_id}")
async def upload_documents(
    job_id: str,
    files: Annotated[list[UploadFile], File(...)],
    doc_types: Annotated[list[str] | None, Form()] = None,
):
    """Validates and stores documents uploaded from the Step 1 form."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    brief = job["brief"]

    from tertulia.crew.crew import llm_from_settings
    llm = llm_from_settings()

    combined, rejected = await _process_documents(files, doc_types, brief, llm)

    if combined:
        existing = job.get("doc_context", "")
        remaining = MAX_DOC_CONTEXT_CHARS - len(existing)
        if remaining > 0:
            trimmed = combined[:remaining]
            job["doc_context"] = (existing + "\n\n" + trimmed).strip() if existing else trimmed
            brief.doc_context = job["doc_context"]

    return {"accepted": len(files) - len(rejected), "rejected": rejected}


@app.post("/api/chat/{job_id}")
async def chat(
    job_id: str,
    message: str = Form(""),
    images: Annotated[list[UploadFile] | None, File()] = None,
    documents: Annotated[list[UploadFile] | None, File()] = None,
    doc_types: Annotated[list[str] | None, Form()] = None,
):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]

    image_data: list[tuple[str, bytes]] = []
    rejected_images = 0
    for img in (images or []):
        raw = await img.read()
        try:
            mime, clean = await asyncio.to_thread(
                _sanitize_chat_image, img.content_type or "image/jpeg", raw
            )
            image_data.append((mime, clean))
        except ValueError:
            rejected_images += 1

    chat_doc_text = ""
    rejected_docs: list[str] = []
    if documents:
        from tertulia.crew.crew import llm_from_settings
        brief = job["brief"]
        chat_doc_text, rejected_docs = await _process_documents(
            documents, doc_types, brief, llm_from_settings()
        )

    return StreamingResponse(
        _stream_chat(
            job_id, message, image_data,
            rejected_count=rejected_images,
            chat_doc_text=chat_doc_text,
            rejected_docs=rejected_docs,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_chat_system_prompt(job: dict) -> str:
    brief: BusinessBrief = job["brief"]
    debate_lines = "\n".join(
        f"  [{m.get('name', m.get('agent', '?'))}]: {m.get('message', '')}"
        for m in (job.get("messages") or [])
    )
    # H-51: only user messages go to the writer context — assistant answers are not user data
    history_lines = "\n".join(
        f"  Usuario: {h['text']}"
        for h in (job.get("chat_history") or [])[:-1]
        if h["role"] == "user"
    )
    doc_context = job.get("doc_context", "")
    return (
        "Eres un consultor experto en viabilidad de negocios. "
        "Responde en español de forma clara, directa y profesional. "
        "No repitas saludos ni preámbulos innecesarios.\n\n"
        # H-50: prohibit inventing data the model doesn't have
        "REGLA ESTRICTA: si no tienes el dato concreto, di exactamente "
        "'No tengo ese dato' — nunca inventes cifras, rangos ni fuentes.\n\n"
        f"CONTEXTO DEL ANÁLISIS:\n"
        f"  Tipo de negocio: {brief.business_type}\n"
        f"  Barrio: {brief.neighbourhood}\n"
        f"  Presupuesto: {brief.budget_eur} EUR\n"
        f"  Superficie: {brief.area_m2} m²\n"
        f"  Notas del usuario: {brief.notes or '(ninguna)'}\n\n"
        + (f"DOCUMENTOS APORTADOS POR EL USUARIO:\n{doc_context}\n\n" if doc_context else "")
        + f"DEBATE DEL EQUIPO:\n{debate_lines or '  (sin debate previo)'}\n\n"
        + (f"PREGUNTAS PREVIAS DEL USUARIO:\n{history_lines}\n\n" if history_lines else "")
        + "Responde SOLO a lo que el usuario acaba de aportar en su mensaje. "
        "No regeneres el informe completo ni uses datos del contexto "
        "que el usuario no haya mencionado explícitamente ahora."
    )


def _build_vision_only_prompt(job: dict) -> str:
    brief: BusinessBrief = job["brief"]
    return (
        f"Eres un analista visual. El usuario está evaluando abrir un {brief.business_type}"
        f" en {brief.neighbourhood}. "
        "Describe brevemente lo que ves en la imagen: tipo de local, estado, aforo estimado, "
        "aspectos positivos y negativos para el negocio. "
        "Solo describe lo que puedes ver. No uses ningún dato financiero ni de contexto externo."
    )


async def _stream_chat(
    job_id: str,
    message: str,
    image_data: list[tuple[str, bytes]] | None = None,
    rejected_count: int = 0,
    chat_doc_text: str = "",
    rejected_docs: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    job = _jobs[job_id]

    if rejected_count:
        noun = "imagen" if rejected_count == 1 else f"{rejected_count} imágenes"
        yield f"data: {json.dumps({'warning': f'No se pudo incluir {noun}: solo se aceptan JPEG y PNG válidos.'})}\n\n"
    for doc_warning in (rejected_docs or []):
        yield f"data: {json.dumps({'warning': doc_warning})}\n\n"

    # Nothing useful left to send: all attachments rejected and no text typed
    if not message and not chat_doc_text and not image_data:
        yield f"data: {json.dumps({'done': True})}\n\n"
        return

    # Build the history label so the context passed to CrewAI at approval reflects attachments
    notes: list[str] = []
    if image_data:
        n = len(image_data)
        notes.append(f"[{n} imagen{'es' if n > 1 else ''} adjunta{'s' if n > 1 else ''}]")
    if chat_doc_text:
        notes.append("[documento adjunto]")
    user_history_text = f"{' '.join(notes)} {message}".strip() if notes else message
    job.setdefault("chat_history", []).append({"role": "user", "text": user_history_text})

    yield f"data: {json.dumps({'thinking': True, 'agent': 'analyst', 'name': 'Analista'})}\n\n"

    response_text: str | None = None
    try:
        from tertulia.crew.crew import llm_from_settings
        from tertulia.guardrails.anonimizacion import _scrub

        # H-53: anonymize PII in the user message before it reaches the LLM
        safe_message = _scrub(message) if message else message

        # Image-only with no text: use a minimal prompt so the LLM only describes what it sees
        if image_data and not safe_message and not chat_doc_text:
            system_prompt = _build_vision_only_prompt(job)
        else:
            system_prompt = _build_chat_system_prompt(job)

        # Build user content: always a list if there are images or doc text
        if image_data or chat_doc_text:
            if safe_message:
                msg_text = safe_message
            elif image_data and not chat_doc_text:
                msg_text = "Analiza esta imagen y comenta brevemente qué ves que sea relevante para el negocio."
            else:
                msg_text = ""
            if chat_doc_text:
                msg_text = (
                    f"{msg_text}\n\nDOCUMENTO ADJUNTO:\n{chat_doc_text}"
                    if msg_text else
                    f"DOCUMENTO ADJUNTO:\n{chat_doc_text}"
                )
            user_content: str | list = [{"text": msg_text}]
            for mime, img_bytes in (image_data or []):
                b64 = base64.b64encode(img_bytes).decode()
                user_content.append({"inlineData": {"mimeType": mime, "data": b64}})
        else:
            user_content = safe_message

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ]
        # Use inlineData (google-genai format) so GeminiCompletion passes images correctly.
        llm = llm_from_settings()
        raw = await asyncio.to_thread(llm.call, messages)
        response_text = raw if isinstance(raw, str) else getattr(raw, "content", str(raw))
        response_text = response_text or ""
    except Exception:
        log.exception("Chat LLM call failed (job=%s, images=%d)", job_id, len(image_data or []))
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

        if not brief.image_paths:
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        llm = llm_from_settings()
        vision_tools = _get_tools("vision", llm)
        if not vision_tools:
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        profile = load_sector(brief.business_type)
        inputs = build_inputs(brief, profile, images=brief.image_paths)

        yield f"data: {json.dumps({'thinking': True, 'agent': 'vision', 'name': 'Berto'})}\n\n"

        # "research" runs both the researcher and vision tasks in the same crew step.
        # Passing [] for "researcher" leaves it with no tools so only the vision task
        # executes; the researcher completes immediately with nothing to call.
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
    # Compute the real verdict on first call (lazy). If the debate was real and
    # the user provided chat_context in step 3, the writer reruns with that
    # context before extracting the traffic light and confidence.
    if not job.get("verdict_ready") and not job.get("debate_simulated", True):
        await _compute_and_cache_verdict(job_id)
    verdict: SchemaVerdict = job.get("verdict") or _skeleton_verdict()
    result = verdict.model_dump()
    result["tokens_used"] = job.get("tokens_used", 0)
    result["simulated"] = job.get("simulated", False)
    result["foursquare_used"] = job.get("foursquare_used", False)
    # H-60: confidence is only reliable when there are real findings to penalise.
    # An empty findings list produces 1.0 by formula, which is misleading.
    findings = job.get("mcp_findings") or job.get("findings") or []
    result["confidence_reliable"] = len(findings) > 0
    return result


class ApproveRequest(BaseModel):
    approved: bool = True


@app.post("/api/approve/{job_id}")
async def approve(job_id: str, req: ApproveRequest):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    graph_config = {"configurable": {"thread_id": job_id}}

    paused_at = job.get("paused_at")
    if paused_at and (datetime.now(timezone.utc) - paused_at).total_seconds() > settings.HUMAN_TIMEOUT_S:
        await asyncio.to_thread(_graph.update_state, graph_config, {"expired": True})
        try:
            final = await asyncio.wait_for(
                asyncio.to_thread(_graph.invoke, None, graph_config), timeout=300.0
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Graph invoke timed out") from None
        _jobs[job_id].update({
            "status": "expired",
            "traces": final.get("traces", []),
            "errors": final.get("errors", []),
            "sources": final.get("sources", []),
            "findings": final.get("findings", []),
            "tokens_used": final.get("tokens_used", 0),
        })
        try:
            await asyncio.to_thread(save_traces, final.get("traces", []), job_id)
        except Exception:
            log.warning("trace persistence failed for job=%s", job_id, exc_info=True)
        return {"ok": False, "reason": "estudio caducado"}

    if not job.get("is_demo"):
        state_update: dict = {"human_approved": req.approved}
        chat_history = job.get("chat_history", [])
        doc_context = job.get("doc_context", "")
        context_parts: list[str] = []
        if doc_context:
            context_parts.append(f"DOCUMENTOS APORTADOS POR EL USUARIO:\n{doc_context}")
        if chat_history:
            history_text = "\n".join(
                f"Usuario: {h['text']}" if h["role"] == "user" else f"Asistente: {h['text']}"
                for h in chat_history
            )
            context_parts.append(f"CONVERSACIÓN DE CONTEXTO:\n{history_text}")
        if context_parts:
            from tertulia.guardrails.anonimizacion import _scrub
            state_update["chat_context"] = _scrub("\n\n".join(context_parts))
        state_update["mcp_research_summary"] = "\n".join(job.get("mcp_research_summary", []))
        # If the verdict endpoint already ran the writer with chat_context (step 4
        # computes the verdict lazily), skip the writer rerun in the graph so we
        # don't call the LLM twice for the same context.
        if job.get("chat_context_precomputed"):
            state_update["chat_context_applied"] = True
        await asyncio.to_thread(_graph.update_state, graph_config, state_update)
        try:
            final = await asyncio.wait_for(
                asyncio.to_thread(_graph.invoke, None, graph_config), timeout=300.0
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Graph invoke timed out") from None
        _jobs[job_id].update({
            "traces": final.get("traces", []),
            "errors": final.get("errors", []),
            "sources": final.get("sources", []),
            "findings": final.get("findings", []),
            "tokens_used": final.get("tokens_used", 0),
        })
        # H-82: if the graph's writer_node rewrote the draft (review loop or chat_context),
        # update the cached draft and recompute the verdict so the PDF reflects the real output.
        new_draft = final.get("draft_report", "")
        if new_draft and new_draft != _jobs[job_id].get("draft_report", ""):
            _jobs[job_id]["draft_report"] = new_draft
            try:
                _jobs[job_id]["verdict"] = _verdict_from_draft(
                    new_draft,
                    _jobs[job_id].get("mcp_findings", []),
                    _jobs[job_id].get("mcp_sources", []),
                )
            except Exception:
                log.warning("verdict recompute from revised draft failed job=%s", job_id, exc_info=True)
        try:
            await asyncio.to_thread(save_traces, final.get("traces", []), job_id)
        except Exception:
            log.warning("trace persistence failed for job=%s", job_id, exc_info=True)

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

    raw_sources = job.get("sources") or []
    pdf_sources: list[ReportSource] = []
    for s in raw_sources:
        d = s.model_dump() if hasattr(s, "model_dump") else dict(s)
        url = d.get("url")
        if not url or d.get("suspicious"):
            continue
        pdf_sources.append(ReportSource(
            title=d.get("title", url),
            url=url,
            source_type=str(d.get("source_type", "")),
            retrieved_at=str(d.get("retrieved_at", "")),
        ))
    for s in (job.get("mcp_sources") or []):
        d = s.model_dump() if hasattr(s, "model_dump") else dict(s)
        url = d.get("url")
        if not url:
            continue
        pdf_sources.append(ReportSource(
            title=d.get("title", url),
            url=url,
            source_type=str(d.get("source_type", "")),
            retrieved_at=str(d.get("retrieved_at", "")),
        ))

    seen_urls: set[str] = set()
    deduped_sources: list[ReportSource] = []
    for s in pdf_sources:
        if s.url and s.url not in seen_urls:
            seen_urls.add(s.url)
            deduped_sources.append(s)
    pdf_sources = deduped_sources

    pdf_findings: list[ReportFinding] = []
    for f in (job.get("mcp_findings") or []):
        d = f.model_dump() if hasattr(f, "model_dump") else dict(f)
        pdf_findings.append(ReportFinding(
            claim=d.get("claim", ""),
            value=d.get("value"),
            unit=d.get("unit"),
        ))

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
        sources=pdf_sources,
        findings=pdf_findings,
        verdict=ReportVerdict(
            signal=report_signal,
            label=verdict.summary,
            confidence=int(verdict.final_confidence * 100),
            reasons=verdict.reasons,
        ),
        generated_on=date.today(),
        simulated=job.get("simulated", False),
        tokens_used=job.get("tokens_used", 0),
        foursquare_used=job.get("foursquare_used", False),
    )

    try:
        from tertulia.report import build_pdf
        pdf_bytes = await asyncio.to_thread(build_pdf, report_data)
    except Exception as exc:
        raise HTTPException(status_code=501, detail=f"PDF generation unavailable: {exc}") from exc
    _jobs[job_id]["status"] = "done"

    filename = "informe_demo.pdf" if job.get("is_demo") else "InformeTertulIA.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_ALLOWED_IMG_SUFFIXES = {".jpg", ".jpeg", ".png"}
_OUTPUTS_DIR = _ROOT / "outputs"
_MAX_IMG_BYTES = 10 * 1024 * 1024  # 10 MB


@app.post("/api/upload/{job_id}")
async def upload_images(job_id: str, files: Annotated[list[UploadFile], File()], request: Request):
    _check_rate_limit(request.client.host, "upload", settings.RATE_LIMIT_UPLOAD)
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
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            img.verify()
            img = Image.open(io.BytesIO(data))  # reopen: verify() exhausts the stream
            buf = io.BytesIO()
            img.save(buf, format=img.format or ("PNG" if Path(name).suffix.lower() == ".png" else "JPEG"))
            data = buf.getvalue()
        except Exception:
            raise HTTPException(status_code=400, detail=f"{name!r} no es una imagen válida") from None
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


@app.get("/api/state/{job_id}")
async def get_job_state(job_id: str):
    """Returns enough state to restore the UI after a page refresh."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    brief: BusinessBrief = job["brief"]
    user_profile = brief.user_profile
    return {
        "status": job.get("status"),
        "messages": job.get("messages", []),
        "chat_history": job.get("chat_history", []),
        "simulated": job.get("simulated", False),
        "debate_simulated": job.get("debate_simulated", False),
        "brief": {
            "business_type": brief.business_type,
            "neighbourhood": brief.neighbourhood,
            "budget_eur": brief.budget_eur,
            "area_m2": brief.area_m2,
            "radius_m": brief.radius_m,
            "notes": brief.notes,
            "user_profile": user_profile.value if hasattr(user_profile, "value") else str(user_profile),
        },
    }


# ── Static files (must come after all API routes) ─────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse(url="/app.html")

app.mount("/assets", StaticFiles(directory=str(_ROOT / "assets")), name="assets")
app.mount("/", StaticFiles(directory=str(_ROOT / "ui")), name="ui")
