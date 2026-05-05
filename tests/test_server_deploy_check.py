import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "server_deploy_check.py"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
LINUX_DIR = REPO_ROOT / "infra" / "linux"
SPEC = importlib.util.spec_from_file_location("server_deploy_check", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
server_deploy_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_deploy_check
SPEC.loader.exec_module(server_deploy_check)


class _FakeJsonResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_server_compose_command_uses_overlay_files() -> None:
    assert server_deploy_check.server_compose_command("config", "--quiet") == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.server.yml",
        "config",
        "--quiet",
    ]


def test_pg_dump_version_command_uses_postgres_service() -> None:
    assert server_deploy_check.pg_dump_version_command("postgres") == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.server.yml",
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "--version",
    ]


def test_backup_check_json_output_requires_check_backup_before_checks(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: calls.append("root"))

    with pytest.raises(SystemExit) as exc_info:
        server_deploy_check.main(["--backup-check-json-output", "evidence.json"])

    assert exc_info.value.code == 2
    assert calls == []


def test_check_backup_evidence_delegates_to_check_only_without_dump(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    def fake_run_check_only(
        root: Path,
        *,
        service: str,
        check_json_output: str,
    ) -> int:
        calls.append((root, service, check_json_output))
        return 0

    monkeypatch.setattr(
        server_deploy_check,
        "_run_postgres_backup_check_only",
        fake_run_check_only,
    )

    result = server_deploy_check.check_backup_evidence(
        tmp_path,
        service="postgres",
        check_json_output=str(tmp_path / "backup-check.json"),
    )

    assert result.status == "ok"
    assert result.ok
    assert calls == [(tmp_path, "postgres", str(tmp_path / "backup-check.json"))]


def test_check_backup_evidence_failure_is_fatal(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        server_deploy_check,
        "_run_postgres_backup_check_only",
        lambda *args, **kwargs: 9,
    )

    result = server_deploy_check.check_backup_evidence(
        tmp_path,
        service="postgres",
        check_json_output=str(tmp_path / "backup-check.json"),
    )

    assert result.status == "fail"
    assert not result.ok
    assert "exit code 9" in result.detail


def test_check_backup_evidence_exception_is_fatal(monkeypatch, tmp_path: Path) -> None:
    def fail_check_only(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(
        server_deploy_check,
        "_run_postgres_backup_check_only",
        fail_check_only,
    )

    result = server_deploy_check.check_backup_evidence(
        tmp_path,
        service="postgres",
        check_json_output=str(tmp_path / "backup-check.json"),
    )

    assert result.status == "fail"
    assert not result.ok
    assert "disk full" in result.detail


def test_find_repo_root_from_nested_path(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    nested = tmp_path / "infra" / "scripts"
    nested.mkdir(parents=True)

    assert server_deploy_check.find_repo_root(nested) == tmp_path


def test_check_env_warns_or_fails_when_missing(tmp_path: Path) -> None:
    warning = server_deploy_check.check_env(tmp_path, strict=False)
    failure = server_deploy_check.check_env(tmp_path, strict=True)

    assert warning.status == "warn"
    assert warning.ok
    assert failure.status == "fail"
    assert not failure.ok


def test_check_env_passes_when_env_exists(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")

    result = server_deploy_check.check_env(tmp_path, strict=True)

    assert result.status == "ok"
    assert result.ok


def test_check_systemd_units_passes_for_current_templates() -> None:
    results = server_deploy_check.check_systemd_units(REPO_ROOT)

    assert all(result.ok for result in results)
    assert "systemd alert Telegram timer" in {result.name for result in results}


def test_check_systemd_units_fails_for_missing_unit_file(tmp_path: Path) -> None:
    root = _copy_linux_templates(tmp_path)
    (root / "infra" / "linux" / "baizefindb-alert-telegram.timer").unlink()

    results = server_deploy_check.check_systemd_units(root)

    present_check = _check_result(results, "systemd unit files present")
    assert present_check.status == "fail"
    assert "baizefindb-alert-telegram.timer" in present_check.detail


def test_check_systemd_units_fails_for_alert_timer_drift(tmp_path: Path) -> None:
    root = _copy_linux_templates(tmp_path)
    timer_path = root / "infra" / "linux" / "baizefindb-alert-telegram.timer"
    timer_path.write_text(
        timer_path.read_text(encoding="utf-8").replace(
            "OnUnitActiveSec=5min",
            "OnUnitActiveSec=10min",
        ),
        encoding="utf-8",
    )

    results = server_deploy_check.check_systemd_units(root)

    timer_check = _check_result(results, "systemd alert Telegram timer")
    assert timer_check.status == "fail"
    assert "OnUnitActiveSec expected 5min" in timer_check.detail


def test_check_systemd_units_fails_for_forbidden_secret_marker(tmp_path: Path) -> None:
    root = _copy_linux_templates(tmp_path)
    service_path = root / "infra" / "linux" / "baizefindb-monitor.service"
    service_path.write_text(
        service_path.read_text(encoding="utf-8")
        + '\nEnvironment="TELEGRAM_BOT_TOKEN=secret-token"\n',
        encoding="utf-8",
    )

    results = server_deploy_check.check_systemd_units(root)

    secret_check = _check_result(
        results,
        "systemd unit files no embedded secrets or alternate delivery",
    )
    assert secret_check.status == "fail"
    assert "telegram_bot_token" in secret_check.detail


def test_build_report_summarizes_ok_warn_and_fail() -> None:
    report = server_deploy_check.build_report(
        [
            server_deploy_check.CheckResult("a", "ok", "ready"),
            server_deploy_check.CheckResult("b", "warn", "slow"),
            server_deploy_check.CheckResult("c", "fail", "bad"),
        ],
    )

    assert report["status"] == "fail"
    assert report["summary"] == {"total": 3, "ok": 1, "warn": 1, "fail": 1}
    assert report["checks"] == [
        {"name": "a", "status": "ok", "detail": "ready"},
        {"name": "b", "status": "warn", "detail": "slow"},
        {"name": "c", "status": "fail", "detail": "bad"},
    ]
    assert isinstance(report["generated_at"], str)


def test_build_report_warns_without_failure() -> None:
    report = server_deploy_check.build_report(
        [
            server_deploy_check.CheckResult("a", "ok"),
            server_deploy_check.CheckResult("b", "warn"),
        ],
    )

    assert report["status"] == "warn"
    assert report["summary"] == {"total": 2, "ok": 1, "warn": 1, "fail": 0}


def test_write_report_creates_parent_directory(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "deploy-check.json"

    server_deploy_check.write_report(output, {"status": "ok"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "ok"}


def test_run_command_handles_utf8_output_and_missing_streams(monkeypatch, tmp_path: Path) -> None:
    class Completed:
        returncode = 0
        stdout = None
        stderr = "状态 ✓"

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(server_deploy_check.subprocess, "run", fake_run)

    result = server_deploy_check.run_command(
        "docker compose ps",
        ["docker", "compose", "ps"],
        tmp_path,
    )

    assert result.status == "ok"
    assert result.detail == "状态 ✓"
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "replace"


def test_check_http_json_fields_passes_for_required_fields(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"ok","service":"BaizeFinDB"}'

    monkeypatch.setattr(server_deploy_check, "urlopen", lambda *args, **kwargs: FakeResponse())

    result = server_deploy_check.check_http_json_fields(
        "http://example.test",
        "/health",
        ("status", "service"),
        timeout=1,
    )

    assert result.status == "ok"
    assert result.ok


def test_check_http_json_fields_fails_for_missing_fields(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    monkeypatch.setattr(server_deploy_check, "urlopen", lambda *args, **kwargs: FakeResponse())

    result = server_deploy_check.check_http_json_fields(
        "http://example.test",
        "/health",
        ("status", "service"),
        timeout=1,
    )

    assert result.status == "fail"
    assert not result.ok
    assert "service" in result.detail


def test_m5_smoke_checks_cover_read_only_core_endpoints(monkeypatch) -> None:
    calls = []

    def fake_check(base_url: str, path: str, required_fields: tuple[str, ...], *, timeout: int):
        calls.append((base_url, path, required_fields, timeout))
        return server_deploy_check.CheckResult(path, "ok")

    def fake_signal_analysis_smoke(base_url: str, *, timeout: int):
        calls.append((base_url, "radar signal analysis smoke", (), timeout))
        return [server_deploy_check.CheckResult("radar signal analysis smoke", "ok")]

    monkeypatch.setattr(server_deploy_check, "check_http_json_fields", fake_check)
    monkeypatch.setattr(
        server_deploy_check,
        "check_radar_signal_analysis_smoke",
        fake_signal_analysis_smoke,
    )

    results = server_deploy_check.check_m5_smoke("http://api.test", timeout=3)

    assert all(result.ok for result in results)
    assert [call[1] for call in calls] == [
        "/health",
        "/health/ready",
        "/ops/overview",
        "/ops/history",
        "/ops/trends",
        "/ops/readiness",
        "/providers/akshare/status",
        "/providers/tushare/status",
        "/providers/tushare/readiness",
        "/radar/overview",
        "/telegram/status",
        "radar signal analysis smoke",
    ]
    ops_call = calls[2]
    assert "server" in ops_call[2]
    assert "alerts" in ops_call[2]
    ops_history_call = calls[3]
    assert "recent_events" in ops_history_call[2]
    assert "failure_summary" in ops_history_call[2]
    ops_trends_call = calls[4]
    assert ops_trends_call[2] == (
        "generated_at",
        "lookback_hours",
        "bucket_count",
        "bucket_seconds",
        "server",
        "buckets",
    )
    ops_readiness_call = calls[5]
    assert "status" in ops_readiness_call[2]
    assert "checks" in ops_readiness_call[2]


def test_radar_signal_analysis_smoke_samples_first_signal_analysis(monkeypatch) -> None:
    requested_paths: list[str] = []

    def fake_urlopen(request, **kwargs):
        requested_paths.append(request.full_url.removeprefix("http://api.test"))
        if request.full_url.endswith("/radar/signals?limit=1"):
            return _FakeJsonResponse([{"id": 42, "priority": "P1"}])
        return _FakeJsonResponse(
            {
                "signal_id": 42,
                "subject_type": "sector",
                "subject_name": "AI Applications",
                "priority": "P1",
                "lifecycle_stage": "developing",
                "review_status": "candidate",
                "analysis_title": "P1 research brief: AI Applications",
                "key_points": [],
                "metric_highlights": [],
                "risk_flags": [],
                "evidence_summary": {},
                "review_summary": {},
                "agent_inputs": {},
                "next_actions": [],
            }
        )

    monkeypatch.setattr(server_deploy_check, "urlopen", fake_urlopen)

    results = server_deploy_check.check_radar_signal_analysis_smoke(
        "http://api.test",
        timeout=2,
    )

    assert [result.status for result in results] == ["ok", "ok"]
    assert requested_paths == [
        "/radar/signals?limit=1",
        "/radar/signals/42/analysis",
    ]


def test_radar_signal_analysis_smoke_warns_when_no_signal_exists(monkeypatch) -> None:
    monkeypatch.setattr(
        server_deploy_check,
        "urlopen",
        lambda *args, **kwargs: _FakeJsonResponse([]),
    )

    results = server_deploy_check.check_radar_signal_analysis_smoke(
        "http://api.test",
        timeout=2,
    )

    assert len(results) == 1
    assert results[0].status == "warn"
    assert results[0].ok
    assert "skipped signal analysis" in results[0].detail


def test_radar_signal_analysis_smoke_fails_for_malformed_signal_list(monkeypatch) -> None:
    monkeypatch.setattr(
        server_deploy_check,
        "urlopen",
        lambda *args, **kwargs: _FakeJsonResponse({"id": 1}),
    )

    results = server_deploy_check.check_radar_signal_analysis_smoke(
        "http://api.test",
        timeout=2,
    )

    assert len(results) == 1
    assert results[0].status == "fail"
    assert "array" in results[0].detail


def test_radar_signal_analysis_smoke_fails_without_integer_signal_id(monkeypatch) -> None:
    monkeypatch.setattr(
        server_deploy_check,
        "urlopen",
        lambda *args, **kwargs: _FakeJsonResponse([{"id": "42"}]),
    )

    results = server_deploy_check.check_radar_signal_analysis_smoke(
        "http://api.test",
        timeout=2,
    )

    assert len(results) == 1
    assert results[0].status == "fail"
    assert "integer id" in results[0].detail


def test_radar_signal_analysis_smoke_fails_for_missing_analysis_field(
    monkeypatch,
) -> None:
    def fake_urlopen(request, **kwargs):
        if request.full_url.endswith("/radar/signals?limit=1"):
            return _FakeJsonResponse([{"id": 7}])
        return _FakeJsonResponse(
            {
                "signal_id": 7,
                "subject_type": "sector",
                "subject_name": "AI Applications",
                "priority": "P1",
                "lifecycle_stage": "developing",
                "review_status": "candidate",
                "analysis_title": "P1 research brief: AI Applications",
                "key_points": [],
                "metric_highlights": [],
                "risk_flags": [],
                "evidence_summary": {},
                "review_summary": {},
                "agent_inputs": {},
            }
        )

    monkeypatch.setattr(server_deploy_check, "urlopen", fake_urlopen)

    results = server_deploy_check.check_radar_signal_analysis_smoke(
        "http://api.test",
        timeout=2,
    )

    assert [result.status for result in results] == ["ok", "fail"]
    assert "next_actions" in results[1].detail


def test_tushare_anns_d_beat_enablement_flag_defaults_off() -> None:
    args = server_deploy_check.build_parser().parse_args([])

    assert args.check_tushare_anns_d_beat_enablement is False


def test_tushare_anns_d_beat_enablement_flag_can_be_enabled() -> None:
    args = server_deploy_check.build_parser().parse_args(
        ["--check-tushare-anns-d-beat-enablement"]
    )

    assert args.check_tushare_anns_d_beat_enablement is True


def test_main_default_does_not_run_tushare_anns_d_beat_enablement(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")

    calls = []

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: server_deploy_check.CheckResult(name, "ok"),
    )
    monkeypatch.setattr(
        server_deploy_check,
        "check_tushare_anns_d_beat_enablement",
        lambda: calls.append("tushare") or server_deploy_check.CheckResult("tushare", "ok"),
    )

    exit_code = server_deploy_check.main([])

    assert exit_code == 0
    assert calls == []


def test_main_default_does_not_run_systemd_unit_check(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")
    calls = []

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: server_deploy_check.CheckResult(name, "ok"),
    )
    monkeypatch.setattr(
        server_deploy_check,
        "check_systemd_units",
        lambda root: calls.append(root) or [],
    )

    exit_code = server_deploy_check.main([])

    assert exit_code == 0
    assert calls == []


def test_main_check_systemd_units_writes_results_to_json(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = _copy_linux_templates(tmp_path)
    (root / ".env").write_text("APP_ENV=server\n")
    output = tmp_path / "evidence" / "deploy-check.json"

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: root)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: server_deploy_check.CheckResult(name, "ok"),
    )

    exit_code = server_deploy_check.main(
        ["--check-systemd-units", "--json-output", str(output)]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    names = {check["name"] for check in report["checks"]}
    assert exit_code == 0
    assert report["status"] == "ok"
    assert "systemd unit files present" in names
    assert "systemd alert Telegram timer" in names


def test_main_json_output_writes_report_and_keeps_console_output(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")
    output = tmp_path / "evidence" / "deploy-check.json"

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: server_deploy_check.CheckResult(name, "ok", "done"),
    )

    exit_code = server_deploy_check.main(["--json-output", str(output)])

    captured = capsys.readouterr()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "[OK] docker compose config" in captured.out
    assert report["status"] == "ok"
    assert report["summary"] == {"fail": 0, "ok": 3, "total": 3, "warn": 0}
    assert report["checks"][0]["name"] == ".env"
    assert report["checks"][0]["status"] == "ok"


def test_main_json_output_records_warning_with_zero_exit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "deploy-check.json"

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: server_deploy_check.CheckResult(name, "ok"),
    )

    exit_code = server_deploy_check.main(["--json-output", str(output)])

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["status"] == "warn"
    assert report["summary"] == {"fail": 0, "ok": 2, "total": 3, "warn": 1}
    assert report["checks"][0]["name"] == ".env"
    assert report["checks"][0]["status"] == "warn"


def test_main_json_output_records_failure_with_nonzero_exit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")
    output = tmp_path / "deploy-check.json"

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: server_deploy_check.CheckResult(name, "fail", "bad"),
    )

    exit_code = server_deploy_check.main(["--json-output", str(output)])

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["status"] == "fail"
    assert report["summary"] == {"fail": 2, "ok": 1, "total": 3, "warn": 0}


def test_main_check_backup_with_evidence_uses_check_only_not_direct_command(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")
    run_command_calls = []
    check_only_calls = []

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: run_command_calls.append((name, command, root))
        or server_deploy_check.CheckResult(name, "ok"),
    )
    monkeypatch.setattr(
        server_deploy_check,
        "_run_postgres_backup_check_only",
        lambda root, *, service, check_json_output: check_only_calls.append(
            (root, service, check_json_output)
        )
        or 0,
    )

    exit_code = server_deploy_check.main(
        [
            "--check-backup",
            "--postgres-service",
            "db",
            "--backup-check-json-output",
            str(tmp_path / "evidence" / "backup-check.json"),
        ],
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[OK] postgres backup check evidence" in captured.out
    assert check_only_calls == [
        (tmp_path, "db", str(tmp_path / "evidence" / "backup-check.json"))
    ]
    assert "postgres pg_dump available" not in [call[0] for call in run_command_calls]


def test_main_check_backup_without_evidence_keeps_direct_pg_dump_check(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")
    run_command_calls = []
    check_only_calls = []

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: run_command_calls.append((name, command, root))
        or server_deploy_check.CheckResult(name, "ok"),
    )
    monkeypatch.setattr(
        server_deploy_check,
        "_run_postgres_backup_check_only",
        lambda *args, **kwargs: check_only_calls.append((args, kwargs)) or 0,
    )

    exit_code = server_deploy_check.main(["--check-backup", "--postgres-service", "db"])

    assert exit_code == 0
    assert check_only_calls == []
    assert (
        "postgres pg_dump available",
        server_deploy_check.pg_dump_version_command("db"),
        tmp_path,
    ) in run_command_calls


def test_main_tushare_anns_d_beat_enablement_warn_exits_zero(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: server_deploy_check.CheckResult(name, "ok"),
    )
    monkeypatch.setattr(
        server_deploy_check,
        "check_tushare_anns_d_beat_enablement",
        lambda: server_deploy_check.CheckResult(
            "Tushare anns_d Beat enablement checklist",
            "warn",
            "status=warn; summary pass=3 warn=3 fail=0",
        ),
    )

    exit_code = server_deploy_check.main(["--check-tushare-anns-d-beat-enablement"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[WARN] Tushare anns_d Beat enablement checklist" in captured.out


def test_main_tushare_anns_d_beat_enablement_fail_exits_nonzero(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("APP_ENV=server\n")

    monkeypatch.setattr(server_deploy_check, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_deploy_check,
        "run_command",
        lambda name, command, root: server_deploy_check.CheckResult(name, "ok"),
    )
    monkeypatch.setattr(
        server_deploy_check,
        "check_tushare_anns_d_beat_enablement",
        lambda: server_deploy_check.CheckResult(
            "Tushare anns_d Beat enablement checklist",
            "fail",
            "status=fail; summary pass=2 warn=1 fail=1; attention gates=beat_interval:fail",
        ),
    )

    exit_code = server_deploy_check.main(["--check-tushare-anns-d-beat-enablement"])

    assert exit_code == 1


def test_tushare_anns_d_beat_enablement_pass_maps_to_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        server_deploy_check,
        "_build_tushare_anns_d_beat_enablement_report",
        lambda: {
            "status": "pass",
            "mode": "offline_no_token",
            "summary": {"pass": 6, "warn": 0, "fail": 0},
            "checklist": [],
        },
    )

    result = server_deploy_check.check_tushare_anns_d_beat_enablement()

    assert result.status == "ok"
    assert result.ok
    assert "summary pass=6 warn=0 fail=0" in result.detail


def test_tushare_anns_d_beat_enablement_warn_is_non_fatal(monkeypatch) -> None:
    monkeypatch.setattr(
        server_deploy_check,
        "_build_tushare_anns_d_beat_enablement_report",
        lambda: {
            "status": "warn",
            "mode": "offline_no_token",
            "summary": {"pass": 3, "warn": 3, "fail": 0},
            "checklist": [
                {"id": "tushare_token", "status": "warn", "details": {"value": None}},
                {"id": "readiness_live_data", "status": "warn"},
            ],
        },
    )

    result = server_deploy_check.check_tushare_anns_d_beat_enablement()

    assert result.status == "warn"
    assert result.ok
    assert "tushare_token:warn" in result.detail
    assert "readiness_live_data:warn" in result.detail


def test_tushare_anns_d_beat_enablement_fail_is_fatal(monkeypatch) -> None:
    monkeypatch.setattr(
        server_deploy_check,
        "_build_tushare_anns_d_beat_enablement_report",
        lambda: {
            "status": "fail",
            "mode": "offline_no_token",
            "summary": {"pass": 2, "warn": 1, "fail": 1},
            "checklist": [{"id": "beat_interval", "status": "fail"}],
        },
    )

    result = server_deploy_check.check_tushare_anns_d_beat_enablement()

    assert result.status == "fail"
    assert not result.ok
    assert "beat_interval:fail" in result.detail


def test_tushare_anns_d_beat_enablement_summary_does_not_leak_token(monkeypatch) -> None:
    monkeypatch.setattr(
        server_deploy_check,
        "_build_tushare_anns_d_beat_enablement_report",
        lambda: {
            "status": "warn",
            "mode": "offline_no_token",
            "summary": {"pass": 5, "warn": 1, "fail": 0},
            "checklist": [
                {
                    "id": "tushare_token",
                    "status": "warn",
                    "message": "token value should not be copied",
                    "details": {"value": "super-secret-token"},
                }
            ],
        },
    )

    result = server_deploy_check.check_tushare_anns_d_beat_enablement()

    assert "super-secret-token" not in result.detail
    assert "token value should not be copied" not in result.detail


def _copy_linux_templates(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(LINUX_DIR, root / "infra" / "linux")
    return root


def _check_result(
    results: list[server_deploy_check.CheckResult],
    name: str,
) -> server_deploy_check.CheckResult:
    for result in results:
        if result.name == name:
            return result
    raise AssertionError(f"missing check result: {name}")
