"""Guardar las trazas de una ejecución en disco (Issue #16).

Hoy las ``TraceEntry`` viven solo en memoria: ``state["traces"]`` en el grafo
y ``_jobs[job_id]["traces"]`` en la API. Si el proceso se reinicia, se pierden.
Este módulo las escribe en ``trazas/<job_id>/traces.jsonl`` para que un tercero
pueda auditarlas después.

Formato: JSON Lines, una traza por línea. Fácil de leer con ``cat`` o ``jq``.
Un directorio por ejecución: los ids de traza (``trc-001``...) se repiten entre
ejecuciones, y separarlos por ``job_id`` evita la colisión.
"""

import re
from pathlib import Path

from tertulia.schemas import TraceEntry

# store.py vive en src/tertulia/trazas/, así que la raíz del repo son 3 niveles arriba.
_REPO_ROOT = Path(__file__).resolve().parents[3]
TRAZAS_DIR = _REPO_ROOT / "trazas"

# Solo letras, números, guiones y guiones bajos. Evita "..", "/" y "\".
_VALID_JOB_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def save_traces(traces: list[TraceEntry], job_id: str) -> Path:
    """Escribe las trazas de una ejecución en ``trazas/<job_id>/traces.jsonl``.

    - Si la lista está vacía, escribe un archivo vacío (no rompe).
    - Si el archivo ya existe, lo sobrescribe: una ejecución, un archivo.
    - Valida ``job_id`` para que no pueda escapar de ``trazas/``.

    Devuelve la ruta escrita. Lanza ``ValueError`` si ``job_id`` no es válido
    y ``OSError`` si no se puede escribir.
    """
    if not job_id or not _VALID_JOB_ID.fullmatch(job_id):
        raise ValueError(f"invalid job_id: {job_id!r}")

    target_dir = TRAZAS_DIR / job_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "traces.jsonl"

    with target_file.open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(trace.model_dump_json())
            handle.write("\n")

    return target_file
