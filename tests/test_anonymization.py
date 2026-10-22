import pytest
from src.tertulia.guardrails.anonimizacion import anonymize_brief, Brief


def make_brief(context: str) -> Brief:
    return Brief(sector="cafe_cowork", neighborhood="Atocha", context=context)


def test_removes_email():
    result = anonymize_brief(make_brief("Contacta con ana@ejemplo.com para más info"))
    assert "[EMAIL]" in result.context
    assert "ana@ejemplo.com" not in result.context


def test_removes_phone():
    result = anonymize_brief(make_brief("Llámame al 612 345 678"))
    assert "[TELÉFONO]" in result.context
    assert "612 345 678" not in result.context


def test_removes_dni():
    result = anonymize_brief(make_brief("El titular es 12345678Z"))
    assert "[DOCUMENTO]" in result.context
    assert "12345678Z" not in result.context


def test_removes_url():
    result = anonymize_brief(make_brief("Ver en https://miempresa.es/local"))
    assert "[URL]" in result.context
    assert "https://" not in result.context


def test_no_context_returns_unchanged():
    brief = Brief(sector="cafe_cowork", neighborhood="Atocha")
    result = anonymize_brief(brief)
    assert result.context is None


def test_clean_context_unchanged():
    text = "Local de 120m2 en planta baja con terraza"
    result = anonymize_brief(make_brief(text))
    assert result.context == text
