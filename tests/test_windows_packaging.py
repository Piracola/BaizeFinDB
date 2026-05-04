from pathlib import Path

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
