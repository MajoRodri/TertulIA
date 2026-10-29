"""Glue between the tools, the sector profiles and the shared contracts (schemas).

Three jobs:
  1. ``break_even_input_from_profile``: build the break-even input from a sector
     profile (config/sectores/*.yaml). Every cost item of the profile that has no
     amount becomes a fixed cost WITHOUT value, so it is reported as missing and
     never invented.
  2. ``break_even_to_findings``: one figure = one Finding (agreed in schemas v2).
     Each missing item becomes a Finding with status ``missing`` and no value.
  3. ``trace_from_execution`` / ``trace_from_break_even`` / ``artifact_finding``:
     the audit-log entry (TraceEntry) of a tool call, and a Finding for a chart.

Ids are assigned by the graph (team decision): these functions take the number to
start from (``start_index``) and the id of the TraceEntry (``trace_id``) as arguments
and never keep a counter of their own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tertulia.crew.sector import SectorProfile
from tertulia.schemas import Finding, FindingStatus, Source, SourceType, TraceEntry
from tertulia.tools.code_exec import ExecutionResult, GeneratedFile
from tertulia.tools.punto_equilibrio import BreakEvenInput, BreakEvenResult, FixedCost

USER_INPUT_SOURCE = "user_input"


def build_cost_labels(profile: SectorProfile) -> dict[str, str]:
    """Devuelve el mapeo {key: label} de los costes fijos del perfil.

    Se pasa a break_even_to_findings() para que los hallazgos muestren
    "Alquiler del local" en vez de "rent".
    """
    return {item.key: item.label for item in profile.fixed_cost_items}


def break_even_input_from_profile(
    profile: SectorProfile,
    *,
    unit_price: float | None = None,
    unit_variable_cost: float | None = None,
    fixed_costs: dict[str, float | None] | None = None,
    known_rent_eur: float | None = None,
    initial_investment: float | None = None,
    expected_monthly_units: float | None = None,
    operating_days_per_month: int = 30,
) -> BreakEvenInput:
    """Build a ``BreakEvenInput`` whose cost items are exactly those of the profile.

    ``fixed_costs`` maps a profile key (``rent``, ``staff``...) to its monthly amount.
    Keys that are not in the profile raise ``ValueError`` (a typo must not silently
    drop a cost). Items without amount stay empty, so they show up as missing.
    ``known_rent_eur`` (``BusinessBrief.known_rent_eur``) fills ``rent`` if the
    profile has it and no amount was given for it.
    """
    amounts = dict(fixed_costs or {})
    profile_keys = {item.key for item in profile.fixed_cost_items}
    unknown = sorted(set(amounts) - profile_keys)
    if unknown:
        raise ValueError(
            f"fixed cost keys not in the {profile.business_type!r} profile: {unknown}. "
            f"Valid keys: {sorted(profile_keys)}"
        )

    items: list[FixedCost] = []
    for item in profile.fixed_cost_items:
        amount = amounts.get(item.key)
        source = None
        if amount is None and item.key == "rent" and known_rent_eur is not None:
            amount, source = known_rent_eur, USER_INPUT_SOURCE
        items.append(FixedCost(item=item.key, monthly_amount=amount, source=source))

    return BreakEvenInput(
        business_type=profile.business_type,
        unit=profile.unit,
        unit_price=unit_price,
        unit_variable_cost=unit_variable_cost,
        fixed_costs=items,
        initial_investment=initial_investment,
        expected_monthly_units=expected_monthly_units,
        operating_days_per_month=operating_days_per_month,
    )


def _fmt(value: float) -> str:
    """Number as it reads in Spanish text: 1.234,5 (no useless decimals)."""
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def _missing_labels(
    result: BreakEvenResult, unit_label: str, cost_labels: dict[str, str]
) -> dict[str, str]:
    labels = {
        "unit_price": f"Precio por {unit_label}",
        "unit_variable_cost": f"Coste variable por {unit_label}",
        "fixed_costs": "Costes fijos mensuales",
    }
    for key in result.missing_data:
        if key.startswith("fixed_cost:"):
            item = key.removeprefix("fixed_cost:")
            labels[key] = cost_labels.get(item, item)
    return labels


def _missing_unit(key: str, unit: str) -> str:
    if key in ("unit_price", "unit_variable_cost"):
        return f"EUR/{unit}"
    return "EUR/month"


def break_even_to_findings(
    result: BreakEvenResult | dict[str, Any],
    *,
    trace_id: str,
    start_index: int = 1,
    agent: str = "analyst",
    unit_label: str | None = None,
    cost_labels: dict[str, str] | None = None,
) -> list[Finding]:
    """Turn a break-even result into Findings (one per figure, one per missing datum).

    ``trace_id`` is the id of the TraceEntry of the tool call; it becomes ``code_ref``.
    ``start_index`` is the number of the first Finding (the graph owns the counter):
    the ids are ``fnd-<start_index>``, ``fnd-<start_index + 1>``...
    ``unit_label`` is the unit in Spanish (``SectorProfile.unit_label``) and
    ``cost_labels`` maps cost keys to their Spanish label.
    """
    if isinstance(result, dict):
        result = BreakEvenResult(**result)
    label = unit_label or result.unit
    cost_labels = cost_labels or {}
    unit = result.unit
    missing_labels = _missing_labels(result, label, cost_labels)

    note = ""
    if result.status == "partial":
        names = ", ".join(
            missing_labels[k] for k in result.missing_data if k.startswith("fixed_cost:")
        )
        note = f" (resultado parcial, sin incluir: {names})" if names else " (resultado parcial)"

    margin_note = (
        " (negativo: el precio no cubre el coste variable)" if result.status == "unviable" else ""
    )

    # (claim, value, unit); None values are skipped
    figures: list[tuple[str, float | int | None, str]] = [
        (
            f"Costes fijos mensuales considerados en el cálculo{note}",
            result.monthly_fixed_costs,
            "EUR/month",
        ),
        (
            f"Margen de contribución por {label}{margin_note}",
            result.unit_contribution_margin,
            f"EUR/{unit}",
        ),
        (
            f"Hacen falta {_fmt(result.break_even_units_monthly or 0)} {label} al mes "
            f"para alcanzar el punto de equilibrio{note}",
            result.break_even_units_monthly,
            f"{unit}/month",
        ),
        (
            f"Equivale a {_fmt(result.break_even_units_daily or 0)} {label} al día{note}",
            result.break_even_units_daily,
            f"{unit}/day",
        ),
        (
            f"Ingresos mensuales necesarios para el punto de equilibrio{note}",
            result.break_even_revenue_monthly,
            "EUR/month",
        ),
        (
            f"Margen de seguridad sobre las ventas esperadas{note}",
            result.safety_margin_pct,
            "%",
        ),
        (
            f"Meses necesarios para recuperar la inversión inicial{note}",
            result.payback_months,
            "months",
        ),
    ]

    findings: list[Finding] = []

    def next_id() -> str:
        return f"fnd-{start_index + len(findings):03d}"

    for claim, value, figure_unit in figures:
        if value is None:
            continue
        findings.append(
            Finding(
                id=next_id(), claim=claim, value=value, unit=figure_unit,
                status=FindingStatus.OK, code_ref=trace_id, agent=agent,
            )
        )  # fmt: skip
    for key in result.missing_data:
        findings.append(
            Finding(
                id=next_id(), claim=f"Sin dato: {missing_labels[key]}", value=None,
                unit=_missing_unit(key, unit), status=FindingStatus.MISSING,
                code_ref=trace_id, agent=agent,
            )
        )  # fmt: skip
    return findings


def artifact_finding(
    file: GeneratedFile,
    claim: str,
    *,
    finding_id: str,
    trace_id: str,
    agent: str = "analyst",
) -> Finding:
    """A Finding for a chart/table produced by ``run_code`` (no value, just the file)."""
    return Finding(
        id=finding_id, claim=claim, status=FindingStatus.OK, code_ref=trace_id,
        artifact_paths=[file.relative_path], agent=agent,
    )  # fmt: skip


def trace_from_execution(
    result: ExecutionResult,
    *,
    trace_id: str,
    actor: str = "analyst",
    tool: str = "code_exec",
    tokens_used: int = 0,
    source_ids: list[str] | None = None,
    finding_ids: list[str] | None = None,
    timestamp: datetime | None = None,
) -> TraceEntry:
    """The audit-log entry of a ``run_code`` call: the full script is stored."""
    return TraceEntry(
        id=trace_id,
        timestamp=timestamp or datetime.now(UTC),
        actor=actor,
        tool=tool,
        code=result.code,
        output={
            "ok": result.ok,
            "stdout": result.stdout,
            "files": [f.relative_path for f in result.files],
            "duration_s": result.duration_s,
        },
        source_ids=source_ids or [],
        finding_ids=finding_ids or [],
        tokens_used=tokens_used,
        error=None if result.ok else f"{result.error_type}: {result.error_message}",
    )


def trace_from_break_even(
    data: BreakEvenInput,
    result: BreakEvenResult,
    *,
    trace_id: str,
    actor: str = "analyst",
    tool: str = "break_even",
    tokens_used: int = 0,
    source_ids: list[str] | None = None,
    finding_ids: list[str] | None = None,
    timestamp: datetime | None = None,
) -> TraceEntry:
    """The audit-log entry of a break-even call: inputs, formula and full output."""
    return TraceEntry(
        id=trace_id,
        timestamp=timestamp or datetime.now(UTC),
        actor=actor,
        tool=tool,
        inputs=data.model_dump(),
        code=result.formula,
        output=result.model_dump(),
        source_ids=source_ids or [],
        finding_ids=finding_ids or [],
        tokens_used=tokens_used,
    )


# --- MCP -> Sources y Findings (Issue #12) ------------------------------------
#
# El servidor MCP devuelve la respuesta de search_competitors con los counts
# reales (confirmed_count, needs_review_count, coverage_note). Convertimos esa
# respuesta en:
#   - Sources: de dónde viene el dato (OSM, Foursquare si se consultó).
#   - Findings: las cifras reales, una por cifra. Sin inventar nada.
#   - Summary: texto en español con las cifras, para que el Writer y la
#     Revisora dejen de leer el texto del crew (que se equivoca) y usen estos
#     números.
# La lista de venues con needs_review=true se convierte en un Finding por venue,
# para que el informe los pueda listar. Los suspicious no generan Finding: ya
# están contados en suspicious_count del servidor.

OSM_TITLE = "OpenStreetMap (Overpass API)"
OSM_URL = "https://www.openstreetmap.org/"
FOURSQUARE_TITLE = "Foursquare Places API"
FOURSQUARE_URL = "https://foursquare.com/"

_CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "cafe": ("cafeterías", "f"),
    "cafeteria": ("cafeterías", "f"),
    "coworking": ("espacios de coworking", "m"),
    "cowork": ("espacios de coworking", "m"),
    "bar": ("bares", "m"),
    "restaurant": ("restaurantes", "m"),
    "restaurante": ("restaurantes", "m"),
}


def _translate_category(raw: str) -> tuple[str, str]:
    """Returns (label, gender) where gender is 'm' or 'f'."""
    return _CATEGORY_LABELS.get(raw.lower(), (raw, "m"))


def _parse_retrieved_at(value: Any) -> datetime:
    """Devuelve un datetime con timezone. Si no se puede, ahora mismo (UTC)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def mcp_response_to_sources_and_findings(
    response: dict,
    *,
    start_source_index: int = 1,
    start_finding_index: int = 1,
) -> tuple[list[Source], list[Finding], str]:
    """Convierte una respuesta de search_competitors en Sources, Findings y summary.

    El summary es texto en español con las cifras reales, listo para añadir al
    ``research_result``. Así el Writer y la Revisora dejan de leer el texto del
    crew (que se equivoca) y usan los números del servidor.
    """
    raw_category = response.get("category", "venues")
    category, gender = _translate_category(raw_category)
    _adj = "confirmadas" if gender == "f" else "confirmados"
    total = response.get("total", 0)
    confirmed = response.get("confirmed_count", 0)
    needs_review = response.get("needs_review_count", 0)
    coverage_note = response.get("coverage_note")
    foursquare_status = response.get("foursquare_status", "not_used")
    retrieved_at = _parse_retrieved_at(response.get("retrieved_at"))
    from_cache = bool(response.get("from_cache", False))

    sources: list[Source] = []
    findings: list[Finding] = []
    next_source = start_source_index
    next_finding = start_finding_index

    osm_id = f"src-{next_source:03d}"
    sources.append(
        Source(
            id=osm_id,
            source_type=SourceType.OPEN_DATA,
            title=OSM_TITLE,
            url=OSM_URL,
            retrieved_at=retrieved_at,
            retrieved_by="mcp.osm_search",
            from_cache=from_cache,
        )
    )
    next_source += 1

    fsq_id: str | None = None
    if foursquare_status == "used":
        fsq_id = f"src-{next_source:03d}"
        sources.append(
            Source(
                id=fsq_id,
                source_type=SourceType.API,
                title=FOURSQUARE_TITLE,
                url=FOURSQUARE_URL,
                retrieved_at=retrieved_at,
                retrieved_by="mcp.foursquare_search",
                from_cache=False,
            )
        )
        next_source += 1

    source_ids = [osm_id] + ([fsq_id] if fsq_id else [])

    if confirmed is not None:
        findings.append(
            Finding(
                id=f"fnd-{next_finding:03d}",
                claim=f"{confirmed} {category} {_adj} en el radio de búsqueda (total: {total})",
                value=confirmed,
                unit=raw_category,
                source_ids=source_ids,
                agent="researcher",
            )
        )
        next_finding += 1

    if needs_review and needs_review > 0:
        findings.append(
            Finding(
                id=f"fnd-{next_finding:03d}",
                claim=f"{needs_review} {category} pendientes de revisión (de un total de {total})",
                value=needs_review,
                unit=raw_category,
                source_ids=source_ids,
                agent="researcher",
            )
        )
        next_finding += 1

    if coverage_note:
        findings.append(
            Finding(
                id=f"fnd-{next_finding:03d}",
                claim=coverage_note,
                value=None,
                source_ids=[osm_id],
                agent="researcher",
            )
        )
        next_finding += 1

    for venue in response.get("venues", []):
        if not venue.get("needs_review"):
            continue
        if venue.get("suspicious"):
            continue
        name = venue.get("name") or "sin nombre"
        reason = venue.get("review_reason") or "pendiente de revisión"
        venue_source = fsq_id if fsq_id else osm_id
        findings.append(
            Finding(
                id=f"fnd-{next_finding:03d}",
                claim=f"'{name}' — {reason}",
                value=None,
                source_ids=[venue_source],
                agent="researcher",
            )
        )
        next_finding += 1

    summary = findings_to_summary(findings, category=category)
    return sources, findings, summary


def findings_to_summary(findings: list[Finding], *, category: str | None = None) -> str:
    """Texto en español con las cifras reales, para el research_result.

    El Writer y la Revisora lo reciben y trabajan con números reales, no con el
    texto del crew que puede equivocarse. Incluye cada claim de los findings
    (que ya lleva el número y la unidad cuando aplica) y la coverage_note.
    """
    header = "Datos del servidor MCP (search_competitors)"
    if category:
        header += f" [{category}]"
    lines = [header + ":"]
    for finding in findings:
        lines.append(f"- {finding.claim}")
    return "\n".join(lines)
