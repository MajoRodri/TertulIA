"""Graph nodes for TertulIA.

Architecture (hybrid, Issue #12):
  - research_node and analyst_node are pass-through: the crew already ran in
    main.py and its output is pre-loaded into graph state before invoke().
  - writer_node preserves the debate draft on round 0; on rounds 1+ it calls
    the real WriterAgent via run_step("writing") with reviewer feedback.
  - reviewer_node always calls the real ReviewerAgent via run_step("review").
  - vision_charts_node runs analyse_image() on any chart paths in findings.

Error policy (Issue #14):
  - Every node is wrapped in try/except: an unexpected exception becomes ERR-008
    and the node returns a safe partial result instead of crashing the graph.
  - Before calling the LLM each node checks the token budget; exhausted budget
    records ERR-006 (fatal: graph goes to human_approval without verdict).
"""

from datetime import datetime, timezone

from tertulia.schemas import Finding, TraceEntry

from .errors import (
    GRAPH_INTERNAL,
    TOKEN_BUDGET_EXHAUSTED,
    TOOL_FAILURE,
    ErrorEntry,
    ErrorSeverity,
)
from .state import AgentState


def _record_error(state: AgentState, error: ErrorEntry) -> dict:
    """Return a state patch that appends ``error`` to ``state["errors"]``."""
    existing = state.get("errors", [])
    return {"errors": existing + [error]}


def _tokens_exhausted(state: AgentState) -> bool:
    """True if the token budget has already been spent."""
    from config.settings import settings  # config/ is outside src/

    return state.get("tokens_used", 0) >= settings.MAX_TOKENS_PER_REPORT


def _budget_error(node: str) -> ErrorEntry:
    """ERR-006: fatal, the graph stops without a verdict."""
    from config.settings import settings  # config/ is outside src/

    return ErrorEntry(
        code=TOKEN_BUDGET_EXHAUSTED,
        node=node,
        severity=ErrorSeverity.FATAL,
        message=(
            "Se ha agotado el presupuesto de tokens del informe. "
            "El estudio se detiene sin veredicto."
        ),
        technical_detail=f"MAX_TOKENS_PER_REPORT = {settings.MAX_TOKENS_PER_REPORT}",
        retryable=False,
    )


def _internal_error(node: str, exc: BaseException) -> ErrorEntry:
    """ERR-008: an unexpected exception inside a node."""
    return ErrorEntry(
        code=GRAPH_INTERNAL,
        node=node,
        severity=ErrorSeverity.FATAL,
        message=f"Error interno en el nodo {node}. El estudio se detiene.",
        technical_detail=f"{type(exc).__name__}: {exc}",
        retryable=False,
    )


def research_node(state: AgentState) -> dict:
    """Pass-through: el crew ya corrió en main.py y sus datos están en state."""
    if _tokens_exhausted(state):
        return _record_error(state, _budget_error("research"))

    try:
        print("[NODO] Investigador: procesando datos recibidos...")
        return {}
    except Exception as exc:  # noqa: BLE001 - any failure must not crash the graph
        print(f"[NODO] Investigador: error interno ({exc}).")
        return _record_error(state, _internal_error("research", exc))


def analyst_node(state: AgentState) -> dict:
    """Pass-through: el crew ya corrió en main.py y sus datos están en state."""
    if _tokens_exhausted(state):
        return _record_error(state, _budget_error("analyst"))

    try:
        print("[NODO] Analista: procesando análisis...")
        return {}
    except Exception as exc:  # noqa: BLE001
        print(f"[NODO] Analista: error interno ({exc}).")
        return _record_error(state, _internal_error("analyst", exc))


def writer_node(state: AgentState) -> dict:
    """Redactor: ronda 0 preserva el borrador del debate; rondas 1+ reescribe con feedback."""
    if _tokens_exhausted(state):
        return _record_error(state, _budget_error("writer"))

    try:
        patch: dict = {}
        if state.get("chat_context"):
            patch["chat_context_applied"] = True

        if state.get("review_round", 0) == 0:
            print("[NODO] Redactor: usando borrador del debate...")
            patch["draft_report"] = state.get("draft_report", "")
            return patch

        print("[NODO] Redactor: reescribiendo con feedback del revisor...")
        from tertulia.crew.crew import llm_from_settings, run_step
        from tertulia.crew.inputs import build_inputs
        from tertulia.crew.sector import load_sector

        brief = state["request"]
        profile = load_sector(brief.business_type)
        inputs = build_inputs(
            brief, profile,
            research_result=state.get("research_result"),
            vision_result=state.get("vision_result"),
            analysis_result=state.get("analysis_result"),
            draft_report=state.get("draft_report"),
            review_feedback=state.get("reviewer_comments"),
            chat_context=state.get("chat_context"),
            mcp_research_summary=state.get("mcp_research_summary"),
        )
        result = run_step("writing", inputs, llm_from_settings())
        patch["draft_report"] = result.get("writing_task") or state.get("draft_report", "")
        return patch
    except Exception as exc:  # noqa: BLE001
        print(f"[NODO] Redactor: error interno ({exc}).")
        error_patch = _record_error(state, _internal_error("writer", exc))
        if state.get("chat_context"):
            error_patch["chat_context_applied"] = True
        return error_patch


def reviewer_node(state: AgentState) -> dict:
    """Revisora: llama al crew real y parsea su veredicto."""
    if _tokens_exhausted(state):
        return _record_error(state, _budget_error("reviewer"))

    try:
        from tertulia.crew.crew import llm_from_settings, review_comments, run_step
        from tertulia.crew.inputs import build_inputs
        from tertulia.crew.sector import load_sector

        brief = state["request"]
        profile = load_sector(brief.business_type)
        inputs = build_inputs(
            brief, profile,
            draft_report=state.get("draft_report"),
            review_feedback=state.get("reviewer_comments"),
            mcp_research_summary=state.get("mcp_research_summary"),
        )
        result = run_step("review", inputs, llm_from_settings())
        comments = review_comments(result.get("review_task", ""))
        print(f"[NODO] Revisora: {'aprobado' if not comments else f'{len(comments)} comentario(s)'}.")
        return {
            "reviewer_comments": comments,
            "review_round": state.get("review_round", 0) + 1,
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[NODO] Revisora: error interno ({exc}).")
        patch = _record_error(state, _internal_error("reviewer", exc))
        patch["reviewer_comments"] = [f"Revisora no disponible: {exc}"]
        patch["review_round"] = state.get("review_round", 0) + 1
        return patch


def vision_charts_node(state: AgentState) -> dict:
    """Analiza los gráficos del Analista con la herramienta de visión (#12).

    - Si el Analista no ha generado gráficos, no hace nada.
    - Para cada gráfico, llama a analyse_image() y comprueba que el modelo lo
      clasificó como "chart" (el kind lo decide el modelo, no el llamador).
    - Crea un Finding por gráfico analizado y una TraceEntry por la llamada.
    - Si un gráfico falla, registra un error degradable y sigue con el siguiente.
    """
    charts: list[str] = []
    for finding in state.get("findings", []):
        for path in finding.artifact_paths:
            if path not in charts:
                charts.append(path)

    if not charts:
        return {}

    if _tokens_exhausted(state):
        return _record_error(state, _budget_error("vision_charts"))

    try:
        from tertulia.crew.crew import llm_from_settings
        from tertulia.vision.loader import ImageRejected
        from tertulia.vision.tool import AnalysisFailed, analyse_image, to_text

        llm = llm_from_settings()
    except Exception as exc:
        return _record_error(state, _internal_error("vision_charts", exc))

    existing_findings = state.get("findings", [])
    existing_traces = state.get("traces", [])
    new_findings: list[Finding] = []
    new_traces: list[TraceEntry] = []
    new_errors: list[ErrorEntry] = []
    next_finding = len(existing_findings) + 1
    next_trace = len(existing_traces) + 1
    tokens_spent = 0

    for path in charts:
        try:
            usage_before = getattr(llm, "token_usage", {}).get("total_tokens", 0)
            analysis = analyse_image(path, llm)
            usage_after = getattr(llm, "token_usage", {}).get("total_tokens", 0)
            tokens_spent += (usage_after - usage_before)
        except (ImageRejected, AnalysisFailed) as exc:
            new_errors.append(
                ErrorEntry(
                    code=TOOL_FAILURE,
                    node="vision_charts",
                    severity=ErrorSeverity.DEGRADABLE,
                    message=f"No se pudo analizar el gráfico {path}.",
                    technical_detail=str(exc),
                    retryable=False,
                )
            )
            continue

        if analysis.kind != "chart":
            new_errors.append(
                ErrorEntry(
                    code=TOOL_FAILURE,
                    node="vision_charts",
                    severity=ErrorSeverity.DEGRADABLE,
                    message=f"El modelo no clasificó {path} como gráfico.",
                    technical_detail=f"kind={analysis.kind}",
                    retryable=False,
                )
            )
            continue

        if analysis.observations:
            claim = analysis.observations[0].observation
        else:
            claim = analysis.unclear or f"Análisis del gráfico {path}"

        text = to_text(analysis)
        trace_id = f"trc-{next_trace:03d}"
        finding_id = f"fnd-{next_finding:03d}"
        new_traces.append(
            TraceEntry(
                id=trace_id,
                timestamp=datetime.now(timezone.utc),
                actor="vision",
                tool="vision.analyse_image",
                inputs={"image_path": path, "kind": analysis.kind.value},
                output=text,
                finding_ids=[finding_id],
            )
        )
        new_findings.append(
            Finding(
                id=finding_id,
                claim=claim,
                agent="vision",
                code_ref=trace_id,
                artifact_paths=[path],
            )
        )
        next_trace += 1
        next_finding += 1

    patch: dict = {}
    if new_findings:
        patch["findings"] = existing_findings + new_findings
    if new_traces:
        patch["traces"] = existing_traces + new_traces
    if new_errors:
        patch["errors"] = state.get("errors", []) + new_errors
    if tokens_spent > 0:
        patch["tokens_used"] = state.get("tokens_used", 0) + tokens_spent
    return patch
