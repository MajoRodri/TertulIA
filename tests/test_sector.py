"""Tests de los perfiles de sector (config/sectores/ + tertulia.crew.sector).

No necesitan claves ni internet: solo leen archivos YAML.
"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from tertulia.crew.sector import (
    SECTORS_DIR,
    SectorNotFoundError,
    SectorProfile,
    list_sectors,
    load_sector,
)

VALID = {
    "business_type": "peluqueria",
    "display_name": "Peluquería",
    "description": "Peluquería de barrio.",
    "unit": "service",
    "unit_label": "servicio",
    "competitor_categories": ["hairdresser"],
    "fixed_cost_items": [{"key": "rent", "label": "Alquiler del local"}],
    "research_questions": ["¿Cuántas peluquerías hay en el barrio?"],
}


def write_profile(folder: Path, name: str, data: dict) -> None:
    (folder / f"{name}.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), "utf-8")


# --- Archivos reales del repo ---------------------------------------------------


def test_demo_profile_loads():
    profile = load_sector("cafe_cowork")
    assert profile.business_type == "cafe_cowork"
    assert {"cafe", "coworking"} <= set(profile.competitor_categories)
    assert "rent" in [item.key for item in profile.fixed_cost_items]


def test_template_is_valid_but_not_listed():
    data = yaml.safe_load((SECTORS_DIR / "_plantilla.yaml").read_text(encoding="utf-8"))
    SectorProfile(**data)  # la plantilla tiene que seguir el modelo
    assert "_plantilla" not in list_sectors()
    assert "cafe_cowork" in list_sectors()


# --- Casos de error (en una carpeta temporal) -----------------------------------


def test_valid_profile_in_temp_folder(tmp_path):
    write_profile(tmp_path, "peluqueria", VALID)
    assert load_sector("peluqueria", tmp_path).unit == "service"


def test_unknown_sector_lists_available(tmp_path):
    write_profile(tmp_path, "peluqueria", VALID)
    with pytest.raises(SectorNotFoundError, match="peluqueria"):
        load_sector("panaderia", tmp_path)


@pytest.mark.parametrize("bad_name", ["../secrets", "Cafe", "cafe cowork", ""])
def test_invalid_names_are_rejected_before_reading(bad_name):
    with pytest.raises(SectorNotFoundError):
        load_sector(bad_name)


def test_empty_file_is_rejected(tmp_path):
    (tmp_path / "vacio.yaml").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_sector("vacio", tmp_path)


def test_file_name_must_match_business_type(tmp_path):
    write_profile(tmp_path, "otro_nombre", VALID)
    with pytest.raises(ValueError, match="must match the file name"):
        load_sector("otro_nombre", tmp_path)


def test_unknown_fields_are_rejected(tmp_path):
    write_profile(tmp_path, "peluqueria", {**VALID, "precio_medio": 15})
    with pytest.raises(ValueError, match="not a valid sector profile"):
        load_sector("peluqueria", tmp_path)


def test_repeated_cost_keys_are_rejected():
    items = [{"key": "rent", "label": "Alquiler"}, {"key": "rent", "label": "Otra vez"}]
    with pytest.raises(ValidationError, match="repeated"):
        SectorProfile(**{**VALID, "fixed_cost_items": items})


def test_profile_is_read_only():
    profile = SectorProfile(**VALID)
    with pytest.raises(ValidationError):
        profile.unit = "ticket"
