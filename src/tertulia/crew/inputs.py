"""Variables que se pueden usar entre llaves en agents.yaml y tasks.yaml.

CrewAI sustituye cada {variable} de los YAML por su valor antes de ejecutar, y
falla si falta alguna. Esta lista es el contrato entre los YAML y crew.py: los
YAML solo pueden usar estas variables, y crew.py (fase 3) tendrá que rellenarlas
todas a partir del BusinessBrief, del perfil de sector y del estado del grafo.
"""

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
        # Del estado del grafo
        "images",
        "review_feedback",
    }
)
