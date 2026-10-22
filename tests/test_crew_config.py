"""Tests de la configuración del crew (agents.yaml y tasks.yaml).

No crean agentes ni llaman a ningún modelo: solo leen los YAML y los comparan con
lo que admite CrewAI. No necesitan claves ni internet.
"""

import re
from pathlib import Path

import pytest
import yaml
from crewai import Agent, Task

from tertulia.crew.inputs import TASK_INPUT_KEYS

CONFIG_DIR = Path(__file__).resolve().parents[1] / "src" / "tertulia" / "crew" / "config"

# Mismos agentes que los valores de Finding.agent que usará el grafo
EXPECTED_AGENTS = {"researcher", "vision", "analyst", "writer", "reviewer"}

# Misma expresión que usa CrewAI para encontrar variables {asi}
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_\-]*)}")


def load(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))


AGENTS = load("agents.yaml")
TASKS = load("tasks.yaml")


def all_texts(config: dict) -> list[str]:
    return [v for item in config.values() for v in item.values() if isinstance(v, str)]


# --- Agentes --------------------------------------------------------------------


def test_expected_agents():
    assert set(AGENTS) == EXPECTED_AGENTS


@pytest.mark.parametrize("name", sorted(EXPECTED_AGENTS))
def test_agent_has_role_goal_backstory(name):
    for field in ("role", "goal", "backstory"):
        assert AGENTS[name].get(field, "").strip(), f"{name} sin {field}"


@pytest.mark.parametrize("name", sorted(EXPECTED_AGENTS))
def test_agent_fields_exist_in_crewai(name):
    unknown = set(AGENTS[name]) - set(Agent.model_fields)
    assert not unknown, f"{name} usa campos que CrewAI no tiene: {unknown}"


@pytest.mark.parametrize("name", sorted(EXPECTED_AGENTS))
def test_agents_do_not_delegate_and_are_limited(name):
    # El grafo orquesta: un agente no debe repartir trabajo a otros
    assert AGENTS[name]["allow_delegation"] is False
    assert 1 <= AGENTS[name]["max_iter"] <= 10


# --- Tareas ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TASKS))
def test_task_fields_exist_in_crewai(name):
    unknown = set(TASKS[name]) - set(Task.model_fields)
    assert not unknown, f"{name} usa campos que CrewAI no tiene: {unknown}"


@pytest.mark.parametrize("name", sorted(TASKS))
def test_task_has_description_output_and_known_agent(name):
    task = TASKS[name]
    assert task["description"].strip() and task["expected_output"].strip()
    assert task["agent"] in AGENTS


def test_every_agent_has_a_task():
    assert {task["agent"] for task in TASKS.values()} == set(AGENTS)


def test_context_only_points_to_earlier_tasks():
    # Las tareas se ejecutan en orden: solo pueden recibir resultados anteriores
    seen: set[str] = set()
    for name, task in TASKS.items():
        for previous in task.get("context", []):
            assert previous in seen, f"{name} usa {previous}, que aún no se ha ejecutado"
        seen.add(name)


# --- Variables {..} -------------------------------------------------------------


USED = {var for text in all_texts(AGENTS) + all_texts(TASKS) for var in PLACEHOLDER.findall(text)}


def test_placeholders_are_known_inputs():
    unknown = USED - TASK_INPUT_KEYS
    assert not unknown, f"variables sin definir en TASK_INPUT_KEYS: {unknown}"


def test_every_input_is_used():
    unused = TASK_INPUT_KEYS - USED
    assert not unused, f"variables que no usa ningún YAML: {unused}"
