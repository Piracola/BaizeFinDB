import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "clients" / "windows" / "run-client.ps1"


def test_launcher_default_runs_gui_without_smoke_check(tmp_path: Path) -> None:
    result, calls = _run_launcher(
        tmp_path,
        "-ServerUrl",
        "http://127.0.0.1:8000",
        "-UserKey",
        "default",
    )

    assert result.returncode == 0
    assert calls == ["-m clients.windows.baizefindb_client"]


def test_launcher_smoke_check_passes_server_user_json_and_strict_args(tmp_path: Path) -> None:
    json_output = tmp_path / "windows-smoke.json"

    result, calls = _run_launcher(
        tmp_path,
        "-ServerUrl",
        "https://api.example.test",
        "-UserKey",
        "tester",
        "-SmokeCheck",
        "-SmokeLookbackHours",
        "6",
        "-SmokeJsonOutput",
        str(json_output),
        "-SmokeStrict",
    )

    assert result.returncode == 0
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url https://api.example.test "
            "--user-key tester --ops-readiness-lookback-hours 6 --json-output "
            f"{json_output} --fail-on-warning"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_launcher_blocks_gui_when_smoke_check_fails(tmp_path: Path) -> None:
    result, calls = _run_launcher(
        tmp_path,
        "-ServerUrl",
        "http://127.0.0.1:8000",
        "-UserKey",
        "default",
        "-SmokeCheck",
        smoke_exit=7,
    )

    assert result.returncode == 7
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url http://127.0.0.1:8000 "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
    ]


def _run_launcher(
    tmp_path: Path,
    *args: str,
    smoke_exit: int = 0,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is required for launcher script checks.")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls_file = tmp_path / "python-calls.txt"
    _write_fake_python(fake_bin / "python.cmd")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["BAIZEFINDB_PYTHON_CALLS"] = str(calls_file)
    env["BAIZEFINDB_FAKE_SMOKE_EXIT"] = str(smoke_exit)
    env["BAIZEFINDB_FAKE_GUI_EXIT"] = "0"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []
    return result, calls


def _write_fake_python(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "@echo off",
                "echo %*>> \"%BAIZEFINDB_PYTHON_CALLS%\"",
                "if \"%1\"==\"-m\" if \"%2\"==\"clients.windows.smoke_check\" "
                "exit /b %BAIZEFINDB_FAKE_SMOKE_EXIT%",
                "if \"%1\"==\"-m\" if \"%2\"==\"clients.windows.baizefindb_client\" "
                "exit /b %BAIZEFINDB_FAKE_GUI_EXIT%",
                "exit /b 0",
            ],
        ),
        encoding="utf-8",
    )
