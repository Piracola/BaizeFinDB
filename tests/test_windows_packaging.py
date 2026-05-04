import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCRIPT = REPO_ROOT / "clients" / "windows" / "package-client.ps1"
GITIGNORE = REPO_ROOT / ".gitignore"


def test_packaging_script_uses_pyinstaller_onedir_for_windows_client_module() -> None:
    script = PACKAGE_SCRIPT.read_text(encoding="utf-8")

    assert "PyInstaller" in script
    assert '"--onedir"' in script
    assert '"--windowed"' in script
    assert '"--name"' in script
    assert '"BaizeFinDB-Windows-Client"' in script
    assert 'runpy.run_module("clients.windows.baizefindb_client", run_name="__main__")' in script


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
