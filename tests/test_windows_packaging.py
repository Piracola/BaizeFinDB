import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCRIPT = REPO_ROOT / "clients" / "windows" / "package-client.ps1"
PACKAGE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "windows-client-package.yml"
GITIGNORE = REPO_ROOT / ".gitignore"
PYPROJECT = REPO_ROOT / "pyproject.toml"
UV_LOCK = REPO_ROOT / "uv.lock"
PACKAGING_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "PROJECT_STATUS.md",
    REPO_ROOT / "docs" / "runbooks" / "windows-client.md",
    REPO_ROOT / "clients" / "windows" / "README.md",
]


def write_fake_python(fake_bin: Path) -> Path:
    fake_python = fake_bin / "python.cmd"
    fake_python.write_text(
        "\n".join(
            [
                "@echo off",
                'if "%EXPECT_PREFLIGHT%"=="1" if not exist "%PYTHON_PREFLIGHT_MARKER%" (',
                '  echo preflight>> "%PYTHON_CALL_LOG%"',
                '  if not "%BAIZE_PACKAGE_PREFLIGHT_REPORT%"=="" (',
                (
                    '    > "%BAIZE_PACKAGE_PREFLIGHT_REPORT%" echo '
                    '{^"python^":{^"status^":^"pass^",'
                    '^"required_version^":^"3.12^",^"version^":^"3.12.0^"},'
                    '^"tkinter^":{^"status^":^"pass^",^"available^":true},'
                    '^"gui_module^":{^"status^":^"pass^",'
                    '^"module^":^"clients.windows.baizefindb_client^",'
                    '^"available^":true}}'
                ),
                "  )",
                '  echo done> "%PYTHON_PREFLIGHT_MARKER%"',
                "  exit /b 0",
                ")",
                'echo pyinstaller>> "%PYTHON_CALL_LOG%"',
                'if "%PYINSTALLER_EXIT_CODE%"=="" (',
                "  exit /b 23",
                ")",
                "exit /b %PYINSTALLER_EXIT_CODE%",
            ]
        ),
        encoding="utf-8",
    )
    return fake_python


def test_packaging_script_uses_pyinstaller_onedir_for_windows_client_module() -> None:
    script = PACKAGE_SCRIPT.read_text(encoding="utf-8")

    assert "PyInstaller" in script
    assert '"--onedir"' in script
    assert '"--windowed"' in script
    assert '"--name"' in script
    assert '"BaizeFinDB-Windows-Client"' in script
    assert '"--hidden-import"' in script
    assert '"clients.windows.baizefindb_client"' in script
    assert '"clients.windows.client_api"' in script
    assert '"clients.windows.smoke_check"' in script
    assert "from clients.windows.baizefindb_client import main" in script
    assert 'os.environ.get("BAIZEFINDB_PACKAGED_IMPORT_CHECK") == "1"' in script
    assert "runpy.run_module" not in script


def test_packaging_script_has_lightweight_python_preflight() -> None:
    script = PACKAGE_SCRIPT.read_text(encoding="utf-8")

    assert "[switch]$SkipPreflight" in script
    assert "[switch]$CheckOnly" in script
    assert "[string]$CheckJsonOutput" in script
    assert "$CheckOnly -and $SkipPreflight" in script
    assert "-CheckJsonOutput can only be used with -CheckOnly" in script
    assert "sys.version_info[:2] != (3, 12)" in script
    assert 'importlib.import_module("tkinter")' in script
    assert 'find_spec("clients.windows.baizefindb_client")' in script
    assert "tk.Tk" not in script


def test_packaging_script_keeps_outputs_under_windows_client_directory() -> None:
    script = PACKAGE_SCRIPT.read_text(encoding="utf-8")

    assert '$DistPath = Join-Path $ScriptDir "dist"' in script
    assert '$WorkPath = Join-Path $ScriptDir "build"' in script
    assert '$SpecPath = Join-Path $WorkPath "spec"' in script
    assert '"--distpath"' in script
    assert '"--workpath"' in script
    assert '"--specpath"' in script
    assert '"--paths"' in script
    assert "$RepoRoot" in script


def test_packaging_outputs_are_gitignored() -> None:
    gitignore = GITIGNORE.read_text(encoding="utf-8")

    assert "clients/windows/build/" in gitignore
    assert "clients/windows/dist/" in gitignore
    assert "clients/windows/package-check-evidence*.json" in gitignore
    assert "*.spec" in gitignore


def test_windows_package_workflow_validates_packaged_imports() -> None:
    workflow = PACKAGE_WORKFLOW.read_text(encoding="utf-8")

    assert "Validate packaged launcher imports" in workflow
    assert "BAIZEFINDB_PACKAGED_IMPORT_CHECK" in workflow
    assert "BaizeFinDB-Windows-Client.exe" in workflow
    assert "$LASTEXITCODE" in workflow


def test_packaging_dependency_group_is_dedicated_and_bounded() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    dependencies = pyproject["project"]["dependencies"]
    dependency_groups = pyproject["dependency-groups"]
    package_group = dependency_groups["package"]

    assert package_group == ["pyinstaller>=6,<7"]
    assert all("pyinstaller" not in dependency.lower() for dependency in dependencies)
    assert all("pyinstaller" not in dependency.lower() for dependency in dependency_groups["dev"])


def test_packaging_dependency_group_is_locked() -> None:
    lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    project_package = next(
        package for package in lock["package"] if package["name"] == "baizefindb"
    )
    locked_package_group = project_package["metadata"]["requires-dev"]["package"]

    assert locked_package_group == [{"name": "pyinstaller", "specifier": ">=6,<7"}]
    assert any(package["name"] == "pyinstaller" for package in lock["package"])


def test_packaging_docs_prefer_reproducible_uv_group_commands() -> None:
    for doc_path in PACKAGING_DOCS:
        text = doc_path.read_text(encoding="utf-8")
        assert "uv pip install pyinstaller" not in text, doc_path
        assert "uv sync --group package" in text, doc_path
        assert "uv run --group package powershell" in text, doc_path


def test_packaging_dry_run_prints_custom_command_without_artifacts(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    dist_path = tmp_path / "custom dist"
    work_path = tmp_path / "custom build"
    env = os.environ.copy()
    env["PATH"] = ""

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE_SCRIPT),
            "-DryRun",
            "-Name",
            "Custom Client",
            "-DistPath",
            str(dist_path),
            "-WorkPath",
            str(work_path),
            "-Clean",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PyInstaller is not installed" not in result.stderr
    assert result.stdout.startswith("python -m PyInstaller --clean --noconfirm --onedir --windowed")
    assert "--name 'Custom Client'" in result.stdout
    assert f"--distpath '{dist_path}'" in result.stdout
    assert f"--workpath '{work_path}'" in result.stdout
    assert f"--specpath '{work_path / 'spec'}'" in result.stdout
    assert "baizefindb_client_launcher.py" in result.stdout
    assert not dist_path.exists()
    assert not work_path.exists()
    assert not (work_path / "spec").exists()
    assert not (work_path / "baizefindb_client_launcher.py").exists()


def test_packaging_preflight_runs_before_pyinstaller_check_without_artifacts(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "python-calls.log"
    write_fake_python(fake_bin)

    dist_path = tmp_path / "dist"
    work_path = tmp_path / "build"
    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    env["PYTHON_CALL_LOG"] = str(call_log)
    env["EXPECT_PREFLIGHT"] = "1"
    env["PYTHON_PREFLIGHT_MARKER"] = str(tmp_path / "preflight.marker")

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE_SCRIPT),
            "-DistPath",
            str(dist_path),
            "-WorkPath",
            str(work_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "PyInstaller is not installed" in result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2
    assert calls[0] == "preflight"
    assert calls[1] == "pyinstaller"
    assert not dist_path.exists()
    assert not work_path.exists()


def test_packaging_skip_preflight_goes_directly_to_pyinstaller_check(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "python-calls.log"
    write_fake_python(fake_bin)

    dist_path = tmp_path / "dist"
    work_path = tmp_path / "build"
    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    env["PYTHON_CALL_LOG"] = str(call_log)
    env["EXPECT_PREFLIGHT"] = "0"
    env["PYTHON_PREFLIGHT_MARKER"] = str(tmp_path / "preflight.marker")

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE_SCRIPT),
            "-SkipPreflight",
            "-DistPath",
            str(dist_path),
            "-WorkPath",
            str(work_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "PyInstaller is not installed" in result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert calls[0] == "pyinstaller"
    assert not dist_path.exists()
    assert not work_path.exists()


def test_packaging_check_only_runs_preflight_and_pyinstaller_check_without_artifacts(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "python-calls.log"
    write_fake_python(fake_bin)

    dist_path = tmp_path / "dist"
    work_path = tmp_path / "build"
    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    env["PYTHON_CALL_LOG"] = str(call_log)
    env["EXPECT_PREFLIGHT"] = "1"
    env["PYTHON_PREFLIGHT_MARKER"] = str(tmp_path / "preflight.marker")
    env["PYINSTALLER_EXIT_CODE"] = "0"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE_SCRIPT),
            "-CheckOnly",
            "-DistPath",
            str(dist_path),
            "-WorkPath",
            str(work_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Packaging prerequisites are available." in result.stdout
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2
    assert calls[0] == "preflight"
    assert calls[1] == "pyinstaller"
    assert not dist_path.exists()
    assert not work_path.exists()
    assert not (work_path / "spec").exists()
    assert not (work_path / "baizefindb_client_launcher.py").exists()


def test_packaging_check_only_rejects_skip_preflight_without_artifacts(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "python-calls.log"
    write_fake_python(fake_bin)

    dist_path = tmp_path / "dist"
    work_path = tmp_path / "build"
    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    env["PYTHON_CALL_LOG"] = str(call_log)
    env["EXPECT_PREFLIGHT"] = "1"
    env["PYTHON_PREFLIGHT_MARKER"] = str(tmp_path / "preflight.marker")

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE_SCRIPT),
            "-CheckOnly",
            "-SkipPreflight",
            "-DistPath",
            str(dist_path),
            "-WorkPath",
            str(work_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "-CheckOnly cannot be used with -SkipPreflight" in result.stderr
    assert not call_log.exists()
    assert not dist_path.exists()
    assert not work_path.exists()


def test_packaging_check_only_writes_success_evidence_without_artifacts(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "python-calls.log"
    write_fake_python(fake_bin)

    dist_path = tmp_path / "dist"
    work_path = tmp_path / "build"
    evidence_path = tmp_path / "package-check-evidence.json"
    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    env["PYTHON_CALL_LOG"] = str(call_log)
    env["EXPECT_PREFLIGHT"] = "1"
    env["PYTHON_PREFLIGHT_MARKER"] = str(tmp_path / "preflight.marker")
    env["PYINSTALLER_EXIT_CODE"] = "0"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE_SCRIPT),
            "-CheckOnly",
            "-CheckJsonOutput",
            str(evidence_path),
            "-DistPath",
            str(dist_path),
            "-WorkPath",
            str(work_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "ok"
    assert evidence["checks"]["python"] == {
        "status": "pass",
        "required_version": "3.12",
        "version": "3.12.0",
    }
    assert evidence["checks"]["tkinter"] == {"status": "pass", "available": True}
    assert evidence["checks"]["gui_module"] == {
        "status": "pass",
        "module": "clients.windows.baizefindb_client",
        "available": True,
    }
    assert evidence["checks"]["pyinstaller"] == {"status": "pass", "available": True}
    assert evidence["command"]["mode"] == "check-only"
    assert evidence["command"]["target_module"] == "clients.windows.baizefindb_client"
    assert evidence["output_paths"]["dist_path"] == str(dist_path)
    assert evidence["output_paths"]["work_path"] == str(work_path)
    assert evidence["output_paths"]["spec_path"] == str(work_path / "spec")
    assert evidence["output_paths"]["check_json_output"] == str(evidence_path)
    assert "environment" not in evidence
    assert "smoke" not in evidence
    assert "backend" not in evidence
    assert not dist_path.exists()
    assert not work_path.exists()


def test_packaging_check_only_writes_failure_evidence_without_artifacts(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "python-calls.log"
    write_fake_python(fake_bin)

    dist_path = tmp_path / "dist"
    work_path = tmp_path / "build"
    evidence_path = tmp_path / "package-check-evidence.json"
    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    env["PYTHON_CALL_LOG"] = str(call_log)
    env["EXPECT_PREFLIGHT"] = "1"
    env["PYTHON_PREFLIGHT_MARKER"] = str(tmp_path / "preflight.marker")

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE_SCRIPT),
            "-CheckOnly",
            "-CheckJsonOutput",
            str(evidence_path),
            "-DistPath",
            str(dist_path),
            "-WorkPath",
            str(work_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "PyInstaller is not installed" in result.stderr
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "fail"
    assert evidence["checks"]["python"]["status"] == "pass"
    assert evidence["checks"]["tkinter"]["status"] == "pass"
    assert evidence["checks"]["gui_module"]["status"] == "pass"
    assert evidence["checks"]["pyinstaller"] == {"status": "fail", "available": False}
    assert not dist_path.exists()
    assert not work_path.exists()


def test_packaging_rejects_check_json_output_without_check_only_without_artifacts(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "python-calls.log"
    write_fake_python(fake_bin)

    dist_path = tmp_path / "dist"
    work_path = tmp_path / "build"
    evidence_path = tmp_path / "package-check-evidence.json"
    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    env["PYTHON_CALL_LOG"] = str(call_log)
    env["EXPECT_PREFLIGHT"] = "1"
    env["PYTHON_PREFLIGHT_MARKER"] = str(tmp_path / "preflight.marker")
    env["PYINSTALLER_EXIT_CODE"] = "0"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACKAGE_SCRIPT),
            "-CheckJsonOutput",
            str(evidence_path),
            "-DistPath",
            str(dist_path),
            "-WorkPath",
            str(work_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "-CheckJsonOutput can only be used with -CheckOnly" in result.stderr
    assert not evidence_path.exists()
    assert not call_log.exists()
    assert not dist_path.exists()
    assert not work_path.exists()
