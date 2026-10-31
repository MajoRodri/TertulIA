"""Prueba manual del crew con el modelo REAL (gasta cuota de la API).

No es un test automático: se ejecuta a mano, desde la raíz del repo:

    python scripts/try_crew.py

Ejecuta solo el paso "research" (Investigador + Visión): 2 tareas, pocas llamadas.
Lee el modelo y la clave de config/settings.py, que a su vez lee tu .env.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]  # para importar config/ y tertulia/

from config.settings import settings  # noqa: E402
from tertulia.crew.crew import llm_from_settings, run_step  # noqa: E402
from tertulia.crew.inputs import build_inputs  # noqa: E402
from tertulia.crew.sector import load_sector  # noqa: E402
from tertulia.schemas import BusinessBrief  # noqa: E402

if not settings.LLM_API_KEY.get_secret_value():
    sys.exit("Falta LLM_API_KEY en tu archivo .env (en la raíz del repo).")

print(f"Modelo: {settings.LLM_PROVIDER}/{settings.LLM_MODEL_NAME}")  # nunca se imprime la clave

brief = BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha")
inputs = build_inputs(brief, load_sector(brief.business_type))
result, tokens = run_step("research", inputs, llm_from_settings())

print(f"\nTokens usados: {tokens}")
for task_name, text in result.items():
    print(f"\n===== {task_name} =====\n{text}")
