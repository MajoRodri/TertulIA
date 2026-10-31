"""pytest configuration: make the project root importable.

``config/`` lives at the project root (outside ``src/``), so it is not found
with ``PYTHONPATH=src`` alone. The ``pytest`` executable does not add the
current directory to ``sys.path`` (``python -m pytest`` does), so tests that
touch the graph fail with ``ModuleNotFoundError: No module named 'config'``.

This conftest adds the project root to ``sys.path`` once, before any test is
collected. It has no effect outside pytest.
"""

import os
import sys
from pathlib import Path

# Must be set before any test module imports builder.py so SqliteSaver uses :memory:
os.environ.setdefault("TESTING", "1")
# Provide a non-empty key so the LLM_API_KEY validator passes during tests.
os.environ.setdefault("LLM_API_KEY", "test-fake-key-for-tests")

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
