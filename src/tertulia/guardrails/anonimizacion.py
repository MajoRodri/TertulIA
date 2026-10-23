import re
from pydantic import BaseModel

from tertulia.schemas.models import BusinessBrief


# ── Input model (matches frontend brief shape) ────────────────
class Brief(BaseModel):
    sector: str
    neighborhood: str
    budget: str | None = None
    area: str | None = None
    context: str | None = None
    profile: str = "analyst"


# ── PII patterns ──────────────────────────────────────────────
_PATTERNS: list[tuple[str, str]] = [
    # Email
    (r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[EMAIL]"),
    # Spanish phone: +34 / 6xx / 7xx / 9xx
    (r"(?:\+34\s?)?[6-9]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}", "[TELÉFONO]"),
    # Spanish DNI / NIE
    (r"\b[XYZ]\d{7}[A-Z]\b|\b\d{8}[A-Z]\b", "[DOCUMENTO]"),
    # Full name heuristic: two or more capitalized words in a row
    (r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,2}\b", "[NOMBRE]"),
    # URLs
    (r"https?://\S+", "[URL]"),
]


def _scrub(text: str) -> str:
    for pattern, placeholder in _PATTERNS:
        text = re.sub(pattern, placeholder, text)
    return text


# ── Public API ────────────────────────────────────────────────
def anonymize_brief(brief: Brief) -> Brief:
    """Return a copy of brief with PII removed from the context field."""
    if not brief.context:
        return brief
    return brief.model_copy(update={"context": _scrub(brief.context)})


def anonymize_business_brief(brief: BusinessBrief) -> BusinessBrief:
    """Return a copy of brief with PII removed from the notes field."""
    if not brief.notes:
        return brief
    return brief.model_copy(update={"notes": _scrub(brief.notes)})
