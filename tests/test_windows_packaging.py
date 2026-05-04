import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCRIPT = REPO_ROOT / "clients" / "windows" / "package-client.ps1"
GITIGNORE = REPO_ROOT / ".gitignore"


def write_fake_python(fake_bin: Path) -> Path:
    fake_python = fake_bin / "python.cmd"
    fake_python.write_text(
        "\n".join(
            [
                "@echo off",
                'if "%EXPECT_PREFLIGHT%"=="1" if not exist "%PYTHON_PREFLIGHT_MARKER%" (',
                '  echo preflight>> "%PYTHON_CALL_LOG%"',
                '  echo done> "%PYTHON_PREFLIGHT_MARKER%"',
                "  exit /b 0",
                ")",
                'echo pyinstaller>> "%PYTHON_CALL_LOG%"',
                "exit /b 23",
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
    assert 'runpy.run_module("clients.windows.baizefindb_client", run_name="__main__")' in script


def test_packaging_script_has_lightweight_python_preflight() -> None:
    script = PACKAGE_SCRIPT.read_text(encoding="utf-8")

    assert "[switch]$SkipPreflight" in script
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
    assert "*.spec" in gitignore


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
