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
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, AsyncGenerator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tertulia.graph.builder import app as _graph
from tertulia.report.models import AgentMessage as ReportMessage
from tertulia.report.models import ReportBrief, ReportData, ReportSource
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

        _tracking: dict = {"foursquare_used": False}

        def _run(step: str, inp: dict) -> dict:
            if step != "research":
                return run_step(step, inp, llm, _tools_map)
            # For the research step, listen for Foursquare usage via MCP events.
            # Import errors mean tracking is unavailable — run without it.
            try:
                import json as _json

                from crewai.events import crewai_event_bus
                from crewai.events.types.mcp_events import MCPToolExecutionCompletedEvent
            except Exception:
                return run_step(step, inp, llm, _tools_map)

            detected = [False]

            def _check(source, event):
                if event.tool_name != "search_competitors":
                    return
                try:
                    r = _json.loads(event.result) if isinstance(event.result, str) else event.result
                    if isinstance(r, dict) and r.get("foursquare_status") == "used":
                        detected[0] = True
                except Exception:
                    pass

            # run_step failures propagate naturally — no retry
            with crewai_event_bus.scoped_handlers():
                crewai_event_bus.on(MCPToolExecutionCompletedEvent)(_check)
                result = run_step(step, inp, llm, _tools_map)
            if detected[0]:
                _tracking["foursquare_used"] = True
            return result

        def _rebuild(acc: dict) -> dict:
            return build_inputs(
                brief,
                profile,
                research_result=acc.get("research_result"),
                vision_result=acc.get("vision_result"),
                analysis_result=acc.get("analysis_result"),
                draft_report=acc.get("draft_report"),
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

    _jobs[job_id]["messages"]          = messages
    _jobs[job_id]["verdict"]           = _skeleton_verdict()
    _jobs[job_id]["status"]            = "paused"
    _jobs[job_id]["debate_simulated"]  = debate_simulated
    _jobs[job_id]["simulated"]         = True  # verdict always skeleton until #12
    _jobs[job_id]["paused_at"]         = datetime.now(timezone.utc)
    _jobs[job_id]["foursquare_used"]   = _tracking.get("foursquare_used", False) if crew else False

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


@app.post("/api/chat/{job_id}")
async def chat(
    job_id: str,
    message: str = Form(...),
    images: Annotated[list[UploadFile] | None, File()] = None,
):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    image_data: list[tuple[str, bytes]] = []
    rejected = 0
    for img in (images or []):
        raw = await img.read()
        try:
            mime, clean = await asyncio.to_thread(
                _sanitize_chat_image, img.content_type or "image/jpeg", raw
            )
            image_data.append((mime, clean))
        except ValueError:
            rejected += 1
    return StreamingResponse(
        _stream_chat(job_id, message, image_data, rejected_count=rejected),
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


async def _stream_chat(
    job_id: str,
    message: str,
    image_data: list[tuple[str, bytes]] | None = None,
    rejected_count: int = 0,
) -> AsyncGenerator[str, None]:
    job = _jobs[job_id]
    job.setdefault("chat_history", []).append({"role": "user", "text": message})

    if rejected_count:
        noun = "imagen" if rejected_count == 1 else f"{rejected_count} imágenes"
        warning = f"No se pudo incluir {noun}: solo se aceptan JPEG y PNG válidos."
        yield f"data: {json.dumps({'warning': warning})}\n\n"

    yield f"data: {json.dumps({'thinking': True, 'agent': 'analyst', 'name': 'Analista'})}\n\n"

    response_text: str | None = None
    try:
        from tertulia.crew.crew import llm_from_settings

        llm = llm_from_settings()
        system_prompt = _build_chat_system_prompt(job)

        if image_data:
            is_gemini = "gemini" in (getattr(llm, "model", "") or "").lower()
            user_content: str | list = [{"type": "text", "text": message}]
            for mime, data in image_data:
                b64 = base64.b64encode(data).decode()
                if is_gemini:
                    user_content.append({"inlineData": {"mimeType": mime, "data": b64}})
                else:
                    user_content.append(
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                    )
        else:
            user_content = message

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
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

    if not job.get("is_demo"):
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
