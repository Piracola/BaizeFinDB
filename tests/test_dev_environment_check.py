import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "dev_environment_check.py"
)
SPEC = importlib.util.spec_from_file_location("dev_environment_check", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
dev_environment_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dev_environment_check
SPEC.loader.exec_module(dev_environment_check)


def test_find_repo_root_from_nested_path(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    nested = tmp_path / "infra" / "scripts"
    nested.mkdir(parents=True)

    assert dev_environment_check.find_repo_root(nested) == tmp_path


def test_server_compose_command_uses_overlay_files() -> None:
    assert dev_environment_check.server_compose_command("config", "--quiet") == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.server.yml",
        "config",
        "--quiet",
    ]


def test_python_version_satisfies_project_requirement(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, requires_python=">=3.12,<3.13")

    ok = dev_environment_check.check_python_version(tmp_path, version_info=(3, 12))
    fail = dev_environment_check.check_python_version(tmp_path, version_info=(3, 13))

    assert ok.status == "ok"
    assert fail.status == "fail"


def test_python_version_warns_when_requirement_missing(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, requires_python=None)

    result = dev_environment_check.check_python_version(tmp_path, version_info=(3, 12))

    assert result.status == "warn"


def test_virtualenv_detects_linux_shape(tmp_path: Path) -> None:
    python_path = tmp_path / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/usr/bin/env python\n")

    result = dev_environment_check.check_virtualenv(tmp_path)

    assert result.status == "ok"


def test_virtualenv_blocks_windows_shape(tmp_path: Path) -> None:
    python_path = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("")

    result = dev_environment_check.check_virtualenv(tmp_path)

    assert result.status == "fail"
    assert "Windows virtualenv" in result.detail


def test_virtualenv_fails_when_missing(tmp_path: Path) -> None:
    result = dev_environment_check.check_virtualenv(tmp_path)

    assert result.status == "fail"
    assert "uv sync --dev" in result.detail


def test_git_worktree_passes_when_clean(monkeypatch, tmp_path: Path) -> None:
    def fake_run_raw(command: list[str], root: Path):
        assert root == tmp_path
        return _completed(stdout="")

    monkeypatch.setattr(dev_environment_check, "run_raw_command", fake_run_raw)

    result = dev_environment_check.check_git_worktree(tmp_path)

    assert result.status == "ok"


def test_git_worktree_reports_crlf_only_dirty(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run_raw(command: list[str], root: Path):
        calls.append(command)
        if command[:2] == ["git", "status"]:
            return _completed(stdout=" M README.md\n")
        return _completed(returncode=0)

    monkeypatch.setattr(dev_environment_check, "run_raw_command", fake_run_raw)

    result = dev_environment_check.check_git_worktree(tmp_path)

    assert result.status == "warn"
    assert "CRLF" in result.detail
    assert "README.md" in result.detail


def test_git_worktree_reports_real_dirty(monkeypatch, tmp_path: Path) -> None:
    def fake_run_raw(command: list[str], root: Path):
        if command[:2] == ["git", "status"]:
            return _completed(stdout=" M backend/app/main.py\n")
        return _completed(returncode=1)

    monkeypatch.setattr(dev_environment_check, "run_raw_command", fake_run_raw)

    result = dev_environment_check.check_git_worktree(tmp_path)

    assert result.status == "warn"
    assert "tracked dirty files" in result.detail


def test_build_report_summarizes_status() -> None:
    report = dev_environment_check.build_report(
        [
            dev_environment_check.CheckResult("a", "ok"),
            dev_environment_check.CheckResult("b", "warn"),
        ],
    )

    assert report["status"] == "warn"
    assert report["summary"] == {"total": 2, "ok": 1, "warn": 1, "fail": 0}


def test_write_report_creates_parent_directory(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "dev-check.json"

    dev_environment_check.write_report(output, {"status": "ok"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "ok"}


def test_main_returns_failure_when_any_check_fails(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "dev-check.json"
    monkeypatch.setattr(dev_environment_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        dev_environment_check,
        "collect_checks",
        lambda root: [dev_environment_check.CheckResult("git worktree", "fail", "dirty")],
    )

    exit_code = dev_environment_check.main(["--json-output", str(output)])

    assert exit_code == 1
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "fail"


def test_main_returns_zero_for_warnings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dev_environment_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        dev_environment_check,
        "collect_checks",
        lambda root: [dev_environment_check.CheckResult("powershell", "warn", "missing")],
    )

    assert dev_environment_check.main([]) == 0


def _write_pyproject(tmp_path: Path, *, requires_python: str | None) -> None:
    if requires_python is None:
        tmp_path.joinpath("pyproject.toml").write_text("[project]\nname='demo'\n")
        return
    tmp_path.joinpath("pyproject.toml").write_text(
        f"[project]\nname='demo'\nrequires-python='{requires_python}'\n",
    )


def _completed(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> object:
    class Completed:
        def __init__(self) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    return Completed()
