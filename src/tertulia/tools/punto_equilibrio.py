"""Break-even tool (punto de equilibrio), generic across sectors (owner: Yohanna).

It knows nothing about cafés: it receives price, variable cost and a list of fixed
costs as DATA. Each sector profile (config/sectores/*.yaml) decides which cost items
are requested; this tool only computes.

If a value is missing it is NOT invented: it computes with what is there, sets the
status ("partial" or "missing"), lists the missing items in ``missing_data`` and
leaves the confidence to the graph (``compute_confidence()`` subtracts a fixed amount
per missing Finding).

Adapter note: one figure = one Finding. Each numeric field of ``BreakEvenResult``
becomes its own Finding (with its unit), all sharing the same ``code_ref`` (the
TraceEntry id of this tool call); every entry of ``missing_data`` becomes a Finding
with status ``missing`` and no value.

"Unit" is whatever the business sells: ticket, customer, cowork seat, service...
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class FixedCost(BaseModel):
    item: str = Field(description="E.g. rent, staff, utilities")
    monthly_amount: float | None = Field(
        default=None, ge=0, description="EUR/month; None = missing"
    )
    source: str | None = Field(default=None, description="Where the figure comes from")


class BreakEvenInput(BaseModel):
    business_type: str = Field(description="Sector profile key, e.g. cafe_cowork")
    unit: str = "ticket"
    unit_price: float | None = Field(default=None, ge=0, description="EUR per unit sold")
    unit_variable_cost: float | None = Field(default=None, ge=0, description="EUR per unit")
    fixed_costs: list[FixedCost] = Field(default_factory=list)
    initial_investment: float | None = Field(default=None, ge=0)
    expected_monthly_units: float | None = Field(default=None, ge=0)
    operating_days_per_month: int = Field(default=30, ge=1, le=31)


class BreakEvenResult(BaseModel):
    status: Literal["ok", "partial", "missing", "unviable"]
    business_type: str
    unit: str
    monthly_fixed_costs: float | None = None
    unit_contribution_margin: float | None = None
    break_even_units_monthly: int | None = None
    break_even_units_daily: float | None = None
    break_even_revenue_monthly: float | None = None
    safety_margin_pct: float | None = None
    payback_months: float | None = None
    missing_data: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)  # Spanish: shown to the user
    formula: str = "break_even_units = fixed_costs / (unit_price - unit_variable_cost)"


def compute_break_even(data: BreakEvenInput) -> BreakEvenResult:
    """Compute the monthly break-even point. Pure, deterministic function."""
    missing: list[str] = []
    if data.unit_price is None:
        missing.append("unit_price")
    if data.unit_variable_cost is None:
        missing.append("unit_variable_cost")
    known_fixed = [c for c in data.fixed_costs if c.monthly_amount is not None]
    missing += [f"fixed_cost:{c.item}" for c in data.fixed_costs if c.monthly_amount is None]
    if not known_fixed:
        missing.append("fixed_costs")

    base = {"business_type": data.business_type, "unit": data.unit}
    if data.unit_price is None or data.unit_variable_cost is None or not known_fixed:
        return BreakEvenResult(
            status="missing", missing_data=missing,
            warnings=["Faltan datos imprescindibles: no se calcula el punto de equilibrio."],
            **base,
        )  # fmt: skip

    fixed = round(sum(c.monthly_amount for c in known_fixed), 2)
    margin = round(data.unit_price - data.unit_variable_cost, 4)
    if margin <= 0:
        return BreakEvenResult(
            status="unviable", monthly_fixed_costs=fixed, unit_contribution_margin=margin,
            missing_data=missing,
            warnings=["El precio no cubre el coste variable: nunca se alcanza el equilibrio."],
            **base,
        )  # fmt: skip

    units = math.ceil(fixed / margin)
    result = BreakEvenResult(
        status="partial" if missing else "ok",
        monthly_fixed_costs=fixed,
        unit_contribution_margin=round(margin, 2),
        break_even_units_monthly=units,
        break_even_units_daily=round(units / data.operating_days_per_month, 2),
        break_even_revenue_monthly=round(units * data.unit_price, 2),
        missing_data=missing,
        **base,
    )
    warnings: list[str] = []
    if missing:
        warnings.append(
            "Resultado parcial: el coste fijo real es MAYOR que el calculado "
            f"(faltan {len(missing)} dato/s)."
        )

    expected = data.expected_monthly_units
    if expected:
        result.safety_margin_pct = round((expected - units) / expected * 100, 1)
        profit = expected * margin - fixed
        if data.initial_investment is not None:
            if profit > 0:
                result.payback_months = round(data.initial_investment / profit, 1)
            else:
                warnings.append("Sin beneficio con esas ventas: no se recupera la inversión.")
    elif data.initial_investment is not None:
        warnings.append("Sin ventas esperadas no se puede estimar el retorno de la inversión.")

    result.warnings = warnings
    return result


# JSON Schema to register the tool in CrewAI / LangChain / MCP.
INPUT_SCHEMA = BreakEvenInput.model_json_schema()


def break_even_tool(**data: Any) -> dict[str, Any]:
    """Agent wrapper: validates, computes and always returns a dict.

    On invalid input it returns ``{"status": "error", ...}`` instead of raising, so the
    graph can handle the tool failure (checklist: «una herramienta que falla»).
    """
    try:
        return compute_break_even(BreakEvenInput(**data)).model_dump()
    except ValidationError as exc:
        errors = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
        return {"status": "error", "errors": errors}
