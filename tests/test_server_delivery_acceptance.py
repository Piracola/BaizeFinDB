import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "server_delivery_acceptance.py"
)
SPEC = importlib.util.spec_from_file_location("server_delivery_acceptance", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
server_delivery_acceptance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_delivery_acceptance
SPEC.loader.exec_module(server_delivery_acceptance)


def test_build_stage_specs_runs_delivery_checks_in_order(tmp_path: Path) -> None:
    args = _args(tmp_path)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "runtime_check",
    ]
    assert stages[0].command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert stages[1].command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--check-backup",
        "--backup-check-json-output",
        str(tmp_path / "postgres-backup-check.json"),
        "--json-output",
        str(tmp_path / "server-backup-preflight.json"),
    ]
    assert stages[2].command == [
        "python",
        "infra/scripts/postgres_backup_retention.py",
        "--json-output",
        str(tmp_path / "postgres-backup-retention.json"),
    ]
    assert "--delete" not in stages[2].command
    assert stages[2].evidence_files == [tmp_path / "postgres-backup-retention.json"]
    assert stages[3].command == [
        "python",
        "infra/scripts/server_runtime_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--samples",
        "3",
        "--interval-seconds",
        "30",
        "--include-ops-trends",
        "--json-output",
        str(tmp_path / "server-runtime-check.json"),
    ]
    assert stages[3].evidence_files == [tmp_path / "server-runtime-check.json"]


def test_build_stage_specs_passes_custom_base_url_to_api_checks(tmp_path: Path) -> None:
    args = _args(tmp_path, base_url="https://api.example.test")

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert "--base-url" in stages[0].command
    assert "https://api.example.test" in stages[0].command
    assert "--base-url" not in stages[1].command
    assert "--base-url" not in stages[2].command
    assert "--base-url" in stages[3].command
    assert "https://api.example.test" in stages[3].command


def test_build_stage_specs_passes_fail_on_warning_to_runtime_only(tmp_path: Path) -> None:
    args = _args(tmp_path, fail_on_warning=True)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert "--fail-on-warning" not in stages[0].command
    assert "--fail-on-warning" not in stages[1].command
    assert "--fail-on-warning" not in stages[2].command
    assert "--fail-on-warning" in stages[3].command


def test_build_stage_specs_includes_optional_ops_evidence(tmp_path: Path) -> None:
    args = _args(tmp_path, include_ops_evidence=True)

    runtime_stage = server_delivery_acceptance.build_stage_specs(args)[3]

    assert "--ops-evidence-output" in runtime_stage.command
    assert str(tmp_path / "server-ops-evidence.json") in runtime_stage.command
    assert runtime_stage.evidence_files == [
        tmp_path / "server-runtime-check.json",
        tmp_path / "server-ops-evidence.json",
    ]


def test_build_stage_specs_supports_runtime_overrides(tmp_path: Path) -> None:
    args = _args(tmp_path, runtime_samples=5, runtime_interval_seconds=7)

    runtime_stage = server_delivery_acceptance.build_stage_specs(args)[3]

    assert "--samples" in runtime_stage.command
    assert "5" in runtime_stage.command
    assert "--interval-seconds" in runtime_stage.command
    assert "7" in runtime_stage.command


def test_build_stage_specs_marks_skipped_stages(tmp_path: Path) -> None:
    args = _args(
        tmp_path,
        skip_backup_check=True,
        skip_backup_retention=True,
        skip_runtime_check=True,
        include_ops_evidence=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert stages[1].name == "backup_check"
    assert stages[1].command == []
    assert stages[2].name == "backup_retention"
    assert stages[2].command == []
    assert stages[3].name == "runtime_check"
    assert stages[3].command == []
    assert stages[3].evidence_files == []


def test_build_stage_specs_can_skip_only_backup_retention(tmp_path: Path) -> None:
    args = _args(tmp_path, skip_backup_retention=True)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert stages[2].name == "backup_retention"
    assert stages[2].command == []
    assert stages[2].evidence_files == []
    assert stages[3].name == "runtime_check"


def test_run_acceptance_runs_all_stages_by_default(monkeypatch, tmp_path: Path) -> None:
    args = _args(tmp_path)
    calls = []

    def fake_run_stage(stage, *, repo_root: Path):
        calls.append(stage.name)
        status = "fail" if stage.name == "deploy_preflight" else "ok"
        return server_delivery_acceptance.StageResult(
            name=stage.name,
            status=status,
            command=stage.command,
            exit_code=1 if status == "fail" else 0,
            evidence_files=stage.evidence_files,
        )

    monkeypatch.setattr(server_delivery_acceptance, "run_stage", fake_run_stage)

    results = server_delivery_acceptance.run_acceptance(args, repo_root=tmp_path)

    assert calls == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "runtime_check",
    ]
    assert [result.status for result in results] == ["fail", "ok", "ok", "ok"]


def test_run_acceptance_fail_fast_stops_after_failure(monkeypatch, tmp_path: Path) -> None:
    args = _args(tmp_path, fail_fast=True)
    calls = []

    def fake_run_stage(stage, *, repo_root: Path):
        calls.append(stage.name)
        return server_delivery_acceptance.StageResult(
            name=stage.name,
            status="fail",
            command=stage.command,
            exit_code=9,
            evidence_files=stage.evidence_files,
        )

    monkeypatch.setattr(server_delivery_acceptance, "run_stage", fake_run_stage)

    results = server_delivery_acceptance.run_acceptance(args, repo_root=tmp_path)

    assert calls == ["deploy_preflight"]
    assert len(results) == 1


def test_run_acceptance_fail_fast_continues_after_warning(monkeypatch, tmp_path: Path) -> None:
    args = _args(tmp_path, fail_fast=True)
    calls = []

    def fake_run_stage(stage, *, repo_root: Path):
        calls.append(stage.name)
        status = "warn" if stage.name == "deploy_preflight" else "fail"
        return server_delivery_acceptance.StageResult(
            name=stage.name,
            status=status,
            command=stage.command,
            exit_code=0 if status == "warn" else 2,
            evidence_files=stage.evidence_files,
        )

    monkeypatch.setattr(server_delivery_acceptance, "run_stage", fake_run_stage)

    results = server_delivery_acceptance.run_acceptance(args, repo_root=tmp_path)

    assert calls == ["deploy_preflight", "backup_check"]
    assert [result.status for result in results] == ["warn", "fail"]


def test_run_stage_promotes_warning_evidence_status(monkeypatch, tmp_path: Path) -> None:
    evidence = tmp_path / "deploy.json"
    evidence.write_text(json.dumps({"status": "warn"}), encoding="utf-8")

    monkeypatch.setattr(
        server_delivery_acceptance.subprocess,
        "run",
        lambda *args, **kwargs: _Completed(returncode=0, stdout="[WARN] deploy"),
    )

    result = server_delivery_acceptance.run_stage(
        server_delivery_acceptance.StageSpec(
            name="deploy_preflight",
            command=["python", "helper.py"],
            evidence_files=[evidence],
        ),
        repo_root=tmp_path,
    )

    assert result.status == "warn"
    assert result.ok
    assert result.evidence_statuses == {str(evidence): "warn"}


def test_run_stage_promotes_optional_ops_evidence_warning(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_evidence = tmp_path / "runtime.json"
    ops_evidence = tmp_path / "ops-evidence.json"
    runtime_evidence.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
    ops_evidence.write_text(json.dumps({"status": "warning"}), encoding="utf-8")

    monkeypatch.setattr(
        server_delivery_acceptance.subprocess,
        "run",
        lambda *args, **kwargs: _Completed(returncode=0),
    )

    result = server_delivery_acceptance.run_stage(
        server_delivery_acceptance.StageSpec(
            name="runtime_check",
            command=["python", "helper.py"],
            evidence_files=[runtime_evidence, ops_evidence],
        ),
        repo_root=tmp_path,
    )

    assert result.status == "warn"
    assert result.evidence_statuses == {
        str(runtime_evidence): "ok",
        str(ops_evidence): "warning",
    }


def test_run_stage_fails_for_missing_optional_ops_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_evidence = tmp_path / "runtime.json"
    ops_evidence = tmp_path / "ops-evidence.json"
    runtime_evidence.write_text(json.dumps({"status": "ok"}), encoding="utf-8")

    monkeypatch.setattr(
        server_delivery_acceptance.subprocess,
        "run",
        lambda *args, **kwargs: _Completed(returncode=0),
    )

    result = server_delivery_acceptance.run_stage(
        server_delivery_acceptance.StageSpec(
            name="runtime_check",
            command=["python", "helper.py"],
            evidence_files=[runtime_evidence, ops_evidence],
        ),
        repo_root=tmp_path,
    )

    assert result.status == "fail"
    assert result.evidence_statuses == {
        str(runtime_evidence): "ok",
        str(ops_evidence): "missing",
    }


def test_run_stage_fails_for_missing_expected_evidence(monkeypatch, tmp_path: Path) -> None:
    evidence = tmp_path / "missing.json"

    monkeypatch.setattr(
        server_delivery_acceptance.subprocess,
        "run",
        lambda *args, **kwargs: _Completed(returncode=0),
    )

    result = server_delivery_acceptance.run_stage(
        server_delivery_acceptance.StageSpec(
            name="deploy_preflight",
            command=["python", "helper.py"],
            evidence_files=[evidence],
        ),
        repo_root=tmp_path,
    )

    assert result.status == "fail"
    assert result.evidence_statuses == {str(evidence): "missing"}


def test_run_stage_fails_for_failing_evidence_despite_zero_exit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "deploy.json"
    evidence.write_text(json.dumps({"status": "blocked"}), encoding="utf-8")

    monkeypatch.setattr(
        server_delivery_acceptance.subprocess,
        "run",
        lambda *args, **kwargs: _Completed(returncode=0),
    )

    result = server_delivery_acceptance.run_stage(
        server_delivery_acceptance.StageSpec(
            name="deploy_preflight",
            command=["python", "helper.py"],
            evidence_files=[evidence],
        ),
        repo_root=tmp_path,
    )

    assert result.status == "fail"
    assert result.evidence_statuses == {str(evidence): "blocked"}


def test_build_report_summarizes_stage_results(tmp_path: Path) -> None:
    report = server_delivery_acceptance.build_report(
        [
            _result("deploy_preflight", "ok", 0),
            _result("backup_check", "warn", 0),
            _result("backup_check", "skipped", None),
            _result("runtime_check", "fail", 2),
        ],
        evidence_dir=tmp_path,
    )

    assert report["status"] == "fail"
    assert report["evidence_dir"] == str(tmp_path)
    assert report["summary"] == {
        "total": 4,
        "ok": 1,
        "warn": 1,
        "fail": 1,
        "skipped": 1,
    }
    assert report["stages"][0]["name"] == "deploy_preflight"
    assert report["stages"][0]["command"] == ["python", "helper.py"]


def test_build_report_warns_without_failure(tmp_path: Path) -> None:
    report = server_delivery_acceptance.build_report(
        [
            _result("deploy_preflight", "warn", 0),
            _result("backup_check", "ok", 0),
        ],
        evidence_dir=tmp_path,
    )

    assert report["status"] == "warn"
    assert report["summary"] == {
        "total": 2,
        "ok": 1,
        "warn": 1,
        "fail": 0,
        "skipped": 0,
    }


def test_write_report_creates_parent_directory(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "acceptance.json"

    server_delivery_acceptance.write_report(output, {"status": "ok"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "ok"}


def test_main_writes_report_and_returns_nonzero_on_failure(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "acceptance.json"

    monkeypatch.setattr(server_delivery_acceptance, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_delivery_acceptance,
        "run_stage",
        lambda stage, *, repo_root: server_delivery_acceptance.StageResult(
            name=stage.name,
            status="fail" if stage.name == "runtime_check" else "ok",
            command=stage.command,
            exit_code=4 if stage.name == "runtime_check" else 0,
            evidence_files=stage.evidence_files,
            stderr="blocked",
        ),
    )

    exit_code = server_delivery_acceptance.main(
        [
            "--evidence-dir",
            str(tmp_path / "evidence"),
            "--json-output",
            str(output),
            "--python-executable",
            "python",
            "--runtime-samples",
            "1",
            "--runtime-interval-seconds",
            "1",
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["status"] == "fail"
    assert report["summary"]["fail"] == 1
    assert "[FAIL] runtime_check exit=4" in captured.out


def test_main_returns_zero_and_reports_warning(monkeypatch, tmp_path: Path, capsys) -> None:
    output = tmp_path / "acceptance.json"

    monkeypatch.setattr(server_delivery_acceptance, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_delivery_acceptance,
        "run_stage",
        lambda stage, *, repo_root: server_delivery_acceptance.StageResult(
            name=stage.name,
            status="warn" if stage.name == "deploy_preflight" else "ok",
            command=stage.command,
            exit_code=0,
            evidence_files=stage.evidence_files,
            evidence_statuses={str(path): "warn" for path in stage.evidence_files},
            stdout="warning-only",
        ),
    )

    exit_code = server_delivery_acceptance.main(
        [
            "--evidence-dir",
            str(tmp_path / "evidence"),
            "--json-output",
            str(output),
            "--python-executable",
            "python",
            "--runtime-samples",
            "1",
            "--runtime-interval-seconds",
            "1",
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["status"] == "warn"
    assert report["summary"]["warn"] == 1
    assert "[WARN] deploy_preflight exit=0" in captured.out
    assert "evidence_statuses=" in captured.out


def test_main_fail_on_warning_returns_nonzero_for_warning_report(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "acceptance.json"

    monkeypatch.setattr(server_delivery_acceptance, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_delivery_acceptance,
        "run_stage",
        lambda stage, *, repo_root: server_delivery_acceptance.StageResult(
            name=stage.name,
            status="warn" if stage.name == "deploy_preflight" else "ok",
            command=stage.command,
            exit_code=0,
            evidence_files=stage.evidence_files,
            evidence_statuses={str(path): "warn" for path in stage.evidence_files},
            stdout="warning-only",
        ),
    )

    exit_code = server_delivery_acceptance.main(
        [
            "--evidence-dir",
            str(tmp_path / "evidence"),
            "--json-output",
            str(output),
            "--python-executable",
            "python",
            "--runtime-samples",
            "1",
            "--runtime-interval-seconds",
            "1",
            "--fail-on-warning",
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["status"] == "warn"
    assert report["summary"]["warn"] == 1
    assert "[WARN] deploy_preflight exit=0" in captured.out


def test_main_rejects_invalid_runtime_samples() -> None:
    with pytest.raises(SystemExit) as exc_info:
        server_delivery_acceptance.main(["--runtime-samples", "0"])

    assert exc_info.value.code == 2


def test_main_rejects_invalid_runtime_interval() -> None:
    with pytest.raises(SystemExit) as exc_info:
        server_delivery_acceptance.main(["--runtime-interval-seconds", "0"])

    assert exc_info.value.code == 2


def _args(tmp_path: Path, **overrides):
    parser = server_delivery_acceptance.build_parser()
    args = parser.parse_args(
        [
            "--evidence-dir",
            str(tmp_path),
            "--python-executable",
            "python",
        ]
    )
    args.json_output = overrides.pop("json_output", None)
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def _result(name: str, status: str, exit_code: int | None):
    return server_delivery_acceptance.StageResult(
        name=name,
        status=status,
        command=["python", "helper.py"],
        exit_code=exit_code,
        evidence_files=[Path("evidence.json")],
        stdout="ok",
        stderr="",
    )


class _Completed:
    def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
