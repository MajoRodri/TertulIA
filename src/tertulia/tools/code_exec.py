"""Code-execution tool for the Analyst agent (pandas + matplotlib).

The agent writes a Python script; this tool runs it in a separate process and returns
stdout, errors and the files the script saved to ``OUTPUT`` (charts, tables...).

Safety layers (defence in depth):
  1. Static analysis (AST): forbidden imports and calls are rejected before running.
  2. Child process with ``python -I``, its own temp directory and a clean environment
     (API keys are NOT inherited).
  3. Hard timeout and, on Linux/macOS, a memory limit.
  4. File guard inside the child (audit hook): the script can only read its own
     folder and the Python/matplotlib files, and can only write inside its own
     folder. It cannot open the project's ``.env`` or any other file of the user,
     whatever the way (``open``, ``pathlib``, ``pandas``...). It also blocks
     starting programs and opening network connections.

NOTE: this is NOT a full sandbox. Against deliberately malicious code a container
would be needed. For our scope (code written by our own agent, no network, no
secrets) it is enough, and it is documented in docs/etica-y-gobernanza.md.

Inside the agent's script these names are available: ``pd``, ``plt``, ``DATA``
(folder with the input files) and ``OUTPUT`` (folder where results must be saved).

Saved files land in ``<outputs_root>/<output_subdir>/`` and are reported both with
their full ``path`` and with a ``relative_path`` (relative to ``outputs/``), which is
the value expected by ``Finding.artifact_paths``.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

FORBIDDEN_IMPORTS = frozenset(
    {
        "os", "sys", "subprocess", "socket", "shutil", "ctypes", "multiprocessing",
        "importlib", "pickle", "builtins", "requests", "urllib", "http", "httpx",
        "ftplib", "smtplib", "telnetlib", "asyncio", "threading", "signal",
    }
)  # fmt: skip
FORBIDDEN_CALLS = frozenset(
    {"eval", "exec", "compile", "__import__", "input", "breakpoint", "globals", "locals"}
)
ALLOWED_EXTENSIONS = frozenset({".png", ".svg", ".csv", ".json", ".txt", ".md"})
MAX_FILES = 10
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_OUTPUT_CHARS = 10_000

_PRELUDE = '''\
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
DATA = "data"
OUTPUT = "output"
'''

# Runs in the child process, after pandas and matplotlib are imported and before the
# agent's code. An audit hook cannot be removed once installed. Everything lives in
# one function so that no helper name stays visible to the agent's script.
_FILE_GUARD = '''
def _tertulia_file_guard():
    import os, sys, sysconfig

    real = os.path.realpath
    work = real(os.getcwd())
    read_roots = {work}
    for p in [*sysconfig.get_paths().values(), sys.prefix, sys.base_prefix,
              sys.exec_prefix, sys.base_exec_prefix]:
        if p:
            read_roots.add(real(p))
    fonts = ["/usr/share/fonts", "/usr/local/share/fonts", "/Library/Fonts",
             "/System/Library/Fonts"]
    if os.environ.get("SYSTEMROOT"):
        fonts.append(os.path.join(os.environ["SYSTEMROOT"], "Fonts"))
    read_roots.update(real(p) for p in fonts)

    def inside(path, roots):
        return any(path == r or path.startswith(r + os.sep) for r in roots)

    def as_path(value):
        if isinstance(value, (str, bytes, os.PathLike)):
            return real(os.fsdecode(value))
        return None  # an open file descriptor, None, a flag...

    blocked = {
        "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
        "subprocess.Popen", "socket.connect", "socket.bind", "socket.getaddrinfo",
        "ctypes.dlopen", "webbrowser.open",
    }
    reads = {"os.listdir", "os.scandir"}
    writes = {
        "os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.truncate", "os.chmod",
        "os.chown", "os.link", "os.symlink", "shutil.copyfile", "shutil.copytree",
        "shutil.move", "shutil.rmtree",
    }
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

    def check(path, roots):
        if not inside(path, roots):
            raise PermissionError(f"acceso bloqueado fuera de la carpeta de trabajo: {path}")

    def guard(event, args):
        if event in blocked:
            raise PermissionError(f"acción bloqueada: {event}")
        if event == "open":
            path = as_path(args[0])
            if path is None:
                return
            mode = args[1] if isinstance(args[1], str) else ""
            flags = args[2] if isinstance(args[2], int) else 0
            writing = any(c in mode for c in "wax+") or bool(flags & write_flags)
            check(path, [work] if writing else read_roots)
        elif event in reads or event in writes:
            for arg in args:
                path = as_path(arg)
                if path is not None:
                    check(path, [work] if event in writes else read_roots)

    sys.addaudithook(guard)


_tertulia_file_guard()
del _tertulia_file_guard
'''

ErrorType = Literal["syntax", "forbidden_code", "timeout", "exception", "internal"]


class GeneratedFile(BaseModel):
    name: str
    path: str = Field(description="Full path on disk")
    relative_path: str = Field(description="Relative to outputs/ (for Finding.artifact_paths)")
    size_bytes: int


class ExecutionResult(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    error_type: ErrorType | None = None
    error_message: str | None = None
    files: list[GeneratedFile] = Field(default_factory=list)
    duration_s: float = 0.0
    code: str = ""  # returned verbatim: the graph stores it in TraceEntry.code


def validate_code(code: str) -> list[str]:
    """Return the problems found (empty list if the code is acceptable).

    Raises ``SyntaxError`` if the code does not compile.
    """
    tree = ast.parse(code)
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                    problems.append(f"import prohibido: {alias.name} (línea {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in FORBIDDEN_IMPORTS:
                problems.append(f"import prohibido: {node.module} (línea {node.lineno})")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FORBIDDEN_CALLS
        ):
            problems.append(f"llamada prohibida: {node.func.id}() (línea {node.lineno})")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            problems.append(f"acceso a atributo especial: {node.attr} (línea {node.lineno})")
    return problems


def _clean_env(workdir: Path) -> dict[str, str]:
    """Minimal environment for the child process: no keys, no user variables."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(workdir),
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": str(workdir / ".mpl"),
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for key in ("SYSTEMROOT", "TEMP", "TMP"):  # needed on Windows
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def _resource_limiter(max_mem_mb: int):
    if os.name != "posix":
        return None

    def _apply() -> None:
        import resource

        limit = max_mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    return _apply


def _prepare_data(data: dict[str, Any] | None, folder: Path) -> None:
    """Copy the input files. ``data`` comes from our own code, never from the agent:
    a file path in it is copied as is, so it must not be built from the agent's text."""
    folder.mkdir()
    for name, content in (data or {}).items():
        safe_name = Path(name).name  # blocks ../ paths
        if hasattr(content, "to_csv"):  # DataFrame
            target = folder / (safe_name if "." in safe_name else f"{safe_name}.csv")
            content.to_csv(target, index=False)
        else:
            shutil.copy(Path(content), folder / safe_name)


def _collect_output(
    output_folder: Path, target_dir: Path, subdir: str, run_id: str
) -> list[GeneratedFile]:
    target_dir.mkdir(parents=True, exist_ok=True)
    collected: list[GeneratedFile] = []
    for file in sorted(output_folder.iterdir()):
        if len(collected) >= MAX_FILES:
            break
        if not file.is_file() or file.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        if file.stat().st_size > MAX_FILE_BYTES:
            continue
        final_name = f"{run_id}_{file.name}"
        final = target_dir / final_name
        shutil.copy(file, final)
        collected.append(
            GeneratedFile(
                name=file.name,
                path=str(final),
                relative_path=f"{subdir}/{final_name}",
                size_bytes=final.stat().st_size,
            )
        )
    return collected


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + "\n[... salida recortada ...]"


def run_code(
    code: str,
    data: dict[str, Any] | None = None,
    *,
    timeout_s: float = 20,
    outputs_root: str | Path = "outputs",
    output_subdir: str = "analysis",
    max_mem_mb: int = 2048,
) -> ExecutionResult:
    """Run ``code`` and return an ``ExecutionResult`` (never raises).

    ``data`` maps name -> DataFrame or file path; the script reads them from ``DATA``.
    Files the script saves to ``OUTPUT`` are copied to ``<outputs_root>/<output_subdir>/``.
    """
    try:
        problems = validate_code(code)
    except SyntaxError as exc:
        return ExecutionResult(
            ok=False, error_type="syntax", error_message=f"{exc.msg} (línea {exc.lineno})",
            code=code,
        )  # fmt: skip
    if problems:
        return ExecutionResult(
            ok=False, error_type="forbidden_code", error_message="; ".join(problems), code=code
        )

    run_id = uuid.uuid4().hex[:8]
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="tertulia_exec_") as tmp:
            workdir = Path(tmp)
            _prepare_data(data, workdir / "data")
            (workdir / "output").mkdir()
            (workdir / "main.py").write_text(_PRELUDE + _FILE_GUARD + "\n" + code, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", "main.py"],
                    cwd=workdir,
                    env=_clean_env(workdir),
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    preexec_fn=_resource_limiter(max_mem_mb),  # noqa: PLW1509
                )
            except subprocess.TimeoutExpired:
                return ExecutionResult(
                    ok=False, error_type="timeout",
                    error_message=f"El código superó el límite de {timeout_s:g} s",
                    duration_s=round(time.monotonic() - start, 2), code=code,
                )  # fmt: skip
            files = _collect_output(
                workdir / "output", Path(outputs_root) / output_subdir, output_subdir, run_id
            )
    except Exception as exc:  # failure of the tool itself, not of the agent's code
        return ExecutionResult(
            ok=False, error_type="internal", error_message=f"{type(exc).__name__}: {exc}",
            code=code,
        )  # fmt: skip

    duration = round(time.monotonic() - start, 2)
    if proc.returncode != 0:
        last_line = (proc.stderr.strip().splitlines() or ["error desconocido"])[-1]
        return ExecutionResult(
            ok=False, stdout=_truncate(proc.stdout), stderr=_truncate(proc.stderr),
            error_type="exception", error_message=last_line, files=files,
            duration_s=duration, code=code,
        )  # fmt: skip
    return ExecutionResult(
        ok=True, stdout=_truncate(proc.stdout), stderr=_truncate(proc.stderr),
        files=files, duration_s=duration, code=code,
    )  # fmt: skip


def run_code_tool(code: str) -> dict[str, Any]:
    """The function to give to the agent (CrewAI/LangGraph): it only accepts ``code``.

    Timeout, memory limit and output folder are fixed. The agent must NOT be able to
    choose ``data`` (paths of files that are copied for it), ``timeout_s`` or
    ``outputs_root``: that is why there is no ``**kwargs`` here. Code of ours that is
    trusted (the graph nodes) calls ``run_code`` directly, with its own ``data``.
    """
    return run_code(code).model_dump()
