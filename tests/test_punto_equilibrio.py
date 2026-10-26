import pytest

from tertulia.tools.punto_equilibrio import (
    BreakEvenInput,
    FixedCost,
    break_even_tool,
    compute_break_even,
)


def _input(**changes):
    base = {
        "business_type": "cafe_cowork",
        "unit_price": 10,
        "unit_variable_cost": 4,
        "fixed_costs": [
            FixedCost(item="rent", monthly_amount=2000),
            FixedCost(item="staff", monthly_amount=1000),
        ],
    }
    base.update(changes)
    return BreakEvenInput(**base)


def test_basic_calculation():
    r = compute_break_even(_input())
    assert r.status == "ok"
    assert r.monthly_fixed_costs == 3000
    assert r.unit_contribution_margin == 6
    assert r.break_even_units_monthly == 500
    assert r.break_even_revenue_monthly == 5000
    assert r.break_even_units_daily == pytest.approx(16.67)
    assert r.missing_data == []


def test_rounds_up():
    r = compute_break_even(
        _input(
            unit_price=4,
            unit_variable_cost=1,
            fixed_costs=[FixedCost(item="rent", monthly_amount=1000)],
        )
    )
    assert r.break_even_units_monthly == 334  # 1000 / 3 = 333.33


def test_safety_margin_and_payback():
    r = compute_break_even(_input(expected_monthly_units=800, initial_investment=12000))
    assert r.safety_margin_pct == 37.5
    assert r.payback_months == pytest.approx(6.7)  # profit 800*6-3000 = 1800


def test_no_profit_means_no_payback():
    r = compute_break_even(_input(expected_monthly_units=400, initial_investment=12000))
    assert r.payback_months is None
    assert any("inversión" in w for w in r.warnings)


def test_fixed_cost_without_value_gives_partial_result():
    data = _input()
    data.fixed_costs.append(FixedCost(item="utilities"))  # no amount
    r = compute_break_even(data)
    assert r.status == "partial"
    assert r.missing_data == ["fixed_cost:utilities"]
    assert r.break_even_units_monthly == 500  # computed with what is known
    assert any("MAYOR" in w for w in r.warnings)


def test_missing_price_is_missing():
    r = compute_break_even(_input(unit_price=None))
    assert r.status == "missing"
    assert "unit_price" in r.missing_data
    assert r.break_even_units_monthly is None


def test_no_fixed_costs_is_missing():
    r = compute_break_even(_input(fixed_costs=[]))
    assert r.status == "missing"
    assert "fixed_costs" in r.missing_data


def test_price_below_variable_cost_is_unviable():
    r = compute_break_even(_input(unit_price=3))
    assert r.status == "unviable"
    assert r.break_even_units_monthly is None


def test_tool_returns_serialisable_dict():
    r = break_even_tool(
        business_type="cafe_cowork",
        unit_price=10,
        unit_variable_cost=4,
        fixed_costs=[{"item": "rent", "monthly_amount": 3000}],
    )
    assert r["status"] == "ok" and r["break_even_units_monthly"] == 500


def test_tool_does_not_raise_on_invalid_input():
    r = break_even_tool(business_type="cafe_cowork", unit_price=-5)
    assert r["status"] == "error"
    assert any("unit_price" in e for e in r["errors"])
