"""Variables que se pueden usar entre llaves en agents.yaml y tasks.yaml.

CrewAI sustituye cada {variable} de los YAML por su valor antes de ejecutar, y
falla (KeyError) si falta alguna. Esta lista es el contrato entre los YAML y
crew.py: los YAML solo pueden usar estas variables y ``build_inputs()`` las
rellena SIEMPRE todas, con un texto por defecto cuando aún no hay dato (por
ejemplo, en la primera ronda no hay comentarios del revisor).
"""

from tertulia.crew.sector import SectorProfile
from tertulia.schemas import BusinessBrief

TASK_INPUT_KEYS: frozenset[str] = frozenset(
    {
        # Del BusinessBrief (la petición de la persona usuaria)
        "neighbourhood",
        "city",
        "budget",
        "known_rent",
        # Del perfil de sector (config/sectores/<business_type>.yaml)
        "display_name",
        "unit_label",
        "competitor_categories",
        "fixed_cost_items",
        "research_questions",
        # Del estado del grafo: resultados de pasos anteriores
        "images",
        "research_result",
        "vision_result",
        "analysis_result",
        "draft_report",
        "review_feedback",
    }
)

# Textos por defecto: nunca una cadena vacía, para que el agente entienda la situación
NO_DATA = "sin dato"
NO_IMAGES = "ninguna"
NO_RESULT = "todavía no disponible"
FIRST_DRAFT = "ninguno (primera redacción)"


def _bullets(items: list[str]) -> str:
    """Convierte una lista en texto con viñetas (CrewAI pondría "['a', 'b']")."""
    return "\n".join(f"- {item}" for item in items)


def _money(amount: float | None) -> str:
    return NO_DATA if amount is None else f"{amount:g} EUR"


def _text(value: str | None, default: str) -> str:
    return value if value and value.strip() else default


def build_inputs(
    brief: BusinessBrief,
    profile: SectorProfile,
    *,
    images: list[str] | None = None,
    research_result: str | None = None,
    vision_result: str | None = None,
    analysis_result: str | None = None,
    draft_report: str | None = None,
    review_feedback: list[str] | None = None,
) -> dict[str, str]:
    """Devuelve las variables de TASK_INPUT_KEYS, todas como texto y ninguna vacía.

    ``images``: si no se pasa, se usan las fotos del encargo (``brief.image_paths``).
    """
    if images is None:
        images = brief.image_paths
    return {
        "neighbourhood": brief.neighbourhood,
        "city": brief.city,
        "budget": _money(brief.budget_eur),
        "known_rent": _money(brief.known_rent_eur),
        "display_name": profile.display_name,
        "unit_label": profile.unit_label,
        "competitor_categories": ", ".join(profile.competitor_categories),
        "fixed_cost_items": _bullets([item.label for item in profile.fixed_cost_items]),
        "research_questions": _bullets(profile.research_questions),
        "images": _bullets(images) if images else NO_IMAGES,
        "research_result": _text(research_result, NO_RESULT),
        "vision_result": _text(vision_result, NO_RESULT),
        "analysis_result": _text(analysis_result, NO_RESULT),
        "draft_report": _text(draft_report, NO_RESULT),
        "review_feedback": _bullets(review_feedback) if review_feedback else FIRST_DRAFT,
    }
