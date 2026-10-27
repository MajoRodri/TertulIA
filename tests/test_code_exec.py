import inspect
import os
from pathlib import Path

import pandas as pd
import pytest

from tertulia.tools.code_exec import _clean_env, run_code, run_code_tool, validate_code


def test_runs_and_captures_stdout(tmp_path):
    r = run_code("print(2 + 2)", outputs_root=tmp_path)
    assert r.ok and r.stdout.strip() == "4"
    assert r.code == "print(2 + 2)"


def test_uses_dataframe_and_generates_chart(tmp_path):
    data = {"sales": pd.DataFrame({"month": ["jan", "feb", "mar"], "eur": [100, 150, 130]})}
    code = (
        "df = pd.read_csv(f'{DATA}/sales.csv')\n"
        "print(df['eur'].sum())\n"
        "df.plot(x='month', y='eur', kind='bar')\n"
        "plt.savefig(f'{OUTPUT}/sales.png')\n"
    )
    r = run_code(code, data=data, outputs_root=tmp_path, output_subdir="run001")
    assert r.ok, r.stderr
    assert r.stdout.strip() == "380"
    assert len(r.files) == 1
    f = r.files[0]
    assert Path(f.path).exists() and f.size_bytes > 0
    assert f.relative_path.startswith("run001/") and f.relative_path.endswith("_sales.png")
    assert (tmp_path / f.relative_path).exists()  # relative to outputs/


def test_rejects_forbidden_imports(tmp_path):
    r = run_code("import os\nos.system('echo hi')", outputs_root=tmp_path)
    assert not r.ok and r.error_type == "forbidden_code"
    assert "os" in r.error_message


def test_rejects_eval_and_dunder_attributes():
    assert validate_code("eval('1+1')")
    assert validate_code("().__class__.__bases__")
    assert validate_code("print(1)") == []


def test_syntax_error(tmp_path):
    r = run_code("print(", outputs_root=tmp_path)
    assert not r.ok and r.error_type == "syntax"


def test_exception_in_code(tmp_path):
    r = run_code("1 / 0", outputs_root=tmp_path)
    assert not r.ok and r.error_type == "exception"
    assert "ZeroDivisionError" in r.error_message


def test_timeout(tmp_path):
    r = run_code("while True:\n    pass", timeout_s=1, outputs_root=tmp_path)
    assert not r.ok and r.error_type == "timeout"


def test_child_env_does_not_inherit_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "secret")
    env = _clean_env(tmp_path)
    assert not any("KEY" in key for key in env)
    assert "ANTHROPIC_API_KEY" in os.environ  # the parent still has it


# --- The agent's code must not read or write files outside its own folder ---------


@pytest.fixture
def secret_file(tmp_path):
    """A file outside the child's folder, like the project's .env."""
    secret = tmp_path / "fake.env"
    secret.write_text("LLM_API_KEY=SECRETO-DE-PRUEBA-1234567890\n", encoding="utf-8")
    return secret


@pytest.mark.parametrize(
    "template",
    [
        "print(open({path!r}).read())",
        "from pathlib import Path\nprint(Path({path!r}).read_text())",
        "print(pd.read_csv({path!r}, header=None))",
    ],
    ids=["open", "pathlib", "pandas"],
)
def test_cannot_read_files_outside_its_folder(tmp_path, secret_file, template):
    r = run_code(template.format(path=str(secret_file)), outputs_root=tmp_path / "outs")
    assert not r.ok and r.error_type == "exception"
    assert "PermissionError" in r.error_message
    assert "SECRETO" not in r.stdout + r.stderr


def test_cannot_write_outside_its_folder(tmp_path):
    target = tmp_path / "pwned.txt"
    r = run_code(f"open({str(target)!r}, 'w').write('x')", outputs_root=tmp_path / "outs")
    assert not r.ok and "PermissionError" in r.error_message
    assert not target.exists()


def test_cannot_start_programs_through_a_library(tmp_path):
    # pandas keeps a reference to the os module: the AST check cannot see this.
    r = run_code("pd.io.common.os.system('echo hola')", outputs_root=tmp_path)
    assert not r.ok and "PermissionError" in r.error_message
    assert "hola" not in r.stdout


def test_can_still_read_its_data_and_save_charts(tmp_path):
    data = {"sales": pd.DataFrame({"month": ["jan", "feb"], "eur": [100, 150]})}
    code = (
        "df = pd.read_csv(f'{DATA}/sales.csv')\n"
        "df.plot(x='month', y='eur')\n"
        "plt.title('Ventas ñ')\n"
        "plt.savefig(f'{OUTPUT}/sales.png')\n"
        "print(df['eur'].sum())\n"
    )
    r = run_code(code, data=data, outputs_root=tmp_path)
    assert r.ok, r.stderr
    assert r.stdout.strip() == "250" and len(r.files) == 1


def test_agent_tool_only_accepts_code(tmp_path, monkeypatch):
    # No **kwargs: the agent cannot pass data (file paths), timeout_s or outputs_root.
    assert list(inspect.signature(run_code_tool).parameters) == ["code"]
    with pytest.raises(TypeError):
        run_code_tool("print(1)", data={"x": "/etc/passwd"})  # type: ignore[call-arg]
    monkeypatch.chdir(tmp_path)
    assert run_code_tool("print(2 + 2)")["stdout"].strip() == "4"
