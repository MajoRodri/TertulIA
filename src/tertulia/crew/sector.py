"""Perfiles de sector: qué buscar y qué costes pedir según el tipo de negocio.

Cada archivo ``config/sectores/<business_type>.yaml`` describe un sector. Añadir un
sector nuevo es añadir un YAML, sin tocar los agentes (plan: «añadir un sector nuevo
no exige tocar código»).

Un perfil NO contiene cifras (ni precios ni alquileres): solo qué buscar y qué
conceptos de coste necesita la herramienta de punto de equilibrio. Los importes
salen siempre de fuentes consultadas o de la persona usuaria, nunca de este archivo.

Lo usan:
- el crew (d: María Isabel), para rellenar las tareas de los agentes;
- ``search_competitors(neighbourhood, category)`` (MCP, Helen), con ``competitor_categories``;
- ``BreakEvenInput`` (herramientas, Yohanna), con ``unit`` y ``fixed_cost_items``.
"""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# src/tertulia/crew/sector.py -> parents[3] es la raíz del repositorio
SECTORS_DIR = Path(__file__).resolve().parents[3] / "config" / "sectores"

KEY_PATTERN = r"^[a-z][a-z0-9_]*$"  # snake_case: seguro como nombre de archivo y como id


class SectorNotFoundError(ValueError):
    """El business_type pedido no tiene perfil en config/sectores/."""


class FixedCostItem(BaseModel):
    """Un coste fijo mensual que hay que conseguir (SIN el importe)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=KEY_PATTERN, examples=["rent"])
    label: str = Field(min_length=1, description="Texto que ve la persona usuaria")


class SectorProfile(BaseModel):
    """Un perfil de sector, cargado desde config/sectores/<business_type>.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    business_type: str = Field(
        pattern=KEY_PATTERN,
        description="Igual que el nombre del archivo y que BusinessBrief.business_type",
        examples=["cafe_cowork"],
    )
    display_name: str = Field(min_length=1, examples=["Café-cowork"])
    description: str = Field(min_length=1)
    unit: str = Field(
        pattern=KEY_PATTERN,
        description="Lo que vende el negocio, para BreakEvenInput.unit",
        examples=["member", "ticket"],
    )
    unit_label: str = Field(min_length=1, description="Nombre de la unidad en español")
    competitor_categories: list[str] = Field(
        min_length=1, description="Valores para search_competitors(category=...)"
    )
    fixed_cost_items: list[FixedCostItem] = Field(min_length=1)
    research_questions: list[str] = Field(
        min_length=1, description="Preguntas para el Investigador, en español"
    )

    @model_validator(mode="after")
    def no_duplicates(self) -> "SectorProfile":
        keys = [item.key for item in self.fixed_cost_items]
        if len(keys) != len(set(keys)):
            raise ValueError("fixed_cost_items has repeated keys")
        if len(self.competitor_categories) != len(set(self.competitor_categories)):
            raise ValueError("competitor_categories has repeated values")
        return self


def list_sectors(sectors_dir: Path = SECTORS_DIR) -> list[str]:
    """Sectores disponibles. Se saltan los archivos que empiezan por "_" (la plantilla)."""
    return sorted(p.stem for p in sectors_dir.glob("*.yaml") if not p.name.startswith("_"))


def load_sector(business_type: str, sectors_dir: Path = SECTORS_DIR) -> SectorProfile:
    """Carga y valida el perfil de ``business_type``.

    Lanza ``SectorNotFoundError`` si no existe ese perfil, y ``ValueError`` si el
    archivo existe pero está vacío, mal escrito o no coincide con su nombre.
    """
    if not re.fullmatch(KEY_PATTERN, business_type):
        # Bloquea nombres como "../secrets" antes de tocar el disco
        raise SectorNotFoundError(f"invalid business_type: {business_type!r}")

    path = sectors_dir / f"{business_type}.yaml"
    if not path.is_file():
        available = ", ".join(list_sectors(sectors_dir)) or "none"
        raise SectorNotFoundError(f"no profile for {business_type!r}. Available: {available}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is empty or is not a YAML mapping")

    try:
        profile = SectorProfile(**data)
    except ValidationError as exc:
        raise ValueError(f"{path.name} is not a valid sector profile:\n{exc}") from exc

    if profile.business_type != business_type:
        raise ValueError(
            f"{path.name} declares business_type={profile.business_type!r}; "
            "it must match the file name"
        )
    return profile
