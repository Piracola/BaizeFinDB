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


def test_build_stage_specs_includes_optional_telegram_strict_binding_check(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_telegram_strict_binding_check=True)

    deploy_stage = server_delivery_acceptance.build_stage_specs(args)[0]

    assert deploy_stage.command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--check-telegram-strict-binding",
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert deploy_stage.evidence_files == [tmp_path / "server-deploy-check.json"]


def test_build_stage_specs_can_require_radar_signal_analysis_sample(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, require_radar_signal_analysis_sample=True)

    deploy_stage = server_delivery_acceptance.build_stage_specs(args)[0]

    assert deploy_stage.command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--require-radar-signal-analysis-sample",
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert deploy_stage.evidence_files == [tmp_path / "server-deploy-check.json"]


def test_build_stage_specs_includes_optional_server_compose_contract_check(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_server_compose_contract_check=True)

    deploy_stage = server_delivery_acceptance.build_stage_specs(args)[0]

    assert deploy_stage.command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--check-server-compose-contract",
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert deploy_stage.evidence_files == [tmp_path / "server-deploy-check.json"]


def test_build_stage_specs_server_compose_contract_check_is_deploy_only(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        include_server_compose_contract_check=True,
        include_alert_telegram_preview=True,
        include_alert_telegram_env_check=True,
        include_alert_telegram_service_verify=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert "--check-server-compose-contract" in stages[0].command
    assert all(
        "--check-server-compose-contract" not in stage.command for stage in stages[1:]
    )


def test_build_stage_specs_telegram_strict_binding_check_is_deploy_only(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        include_telegram_strict_binding_check=True,
        include_alert_telegram_preview=True,
        include_alert_telegram_env_check=True,
        include_alert_telegram_service_verify=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert "--check-telegram-strict-binding" in stages[0].command
    assert all(
        "--check-telegram-strict-binding" not in stage.command for stage in stages[1:]
    )


def test_build_stage_specs_includes_optional_systemd_unit_check(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_systemd_unit_check=True)

    deploy_stage = server_delivery_acceptance.build_stage_specs(args)[0]

    assert deploy_stage.command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--check-systemd-units",
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert deploy_stage.evidence_files == [tmp_path / "server-deploy-check.json"]


def test_build_stage_specs_systemd_unit_check_is_deploy_only(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        include_systemd_unit_check=True,
        include_alert_telegram_preview=True,
        include_alert_telegram_env_check=True,
        include_alert_telegram_service_verify=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert "--check-systemd-units" in stages[0].command
    assert all("--check-systemd-units" not in stage.command for stage in stages[1:])
    assert all("systemctl" not in stage.command for stage in stages)
    assert all("journalctl" not in stage.command for stage in stages)


def test_build_stage_specs_includes_optional_tushare_beat_enablement(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_tushare_anns_d_beat_enablement=True)

    deploy_stage = server_delivery_acceptance.build_stage_specs(args)[0]

    assert deploy_stage.command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--check-tushare-anns-d-beat-enablement",
        "--tushare-anns-d-beat-enablement-json-output",
        str(tmp_path / "tushare-anns-d-beat-enablement.json"),
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert deploy_stage.evidence_files == [
        tmp_path / "server-deploy-check.json",
        tmp_path / "tushare-anns-d-beat-enablement.json",
    ]


def test_build_stage_specs_tushare_beat_enablement_is_deploy_only(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        include_systemd_unit_check=True,
        include_tushare_anns_d_beat_enablement=True,
        include_alert_telegram_preview=True,
        include_alert_telegram_env_check=True,
        include_alert_telegram_service_verify=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert stages[0].command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--check-systemd-units",
        "--check-tushare-anns-d-beat-enablement",
        "--tushare-anns-d-beat-enablement-json-output",
        str(tmp_path / "tushare-anns-d-beat-enablement.json"),
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert stages[0].evidence_files == [
        tmp_path / "server-deploy-check.json",
        tmp_path / "tushare-anns-d-beat-enablement.json",
    ]
    assert all(
        "--check-tushare-anns-d-beat-enablement" not in stage.command
        for stage in stages[1:]
    )
    assert all(
        "--tushare-anns-d-beat-enablement-json-output" not in stage.command
        for stage in stages[1:]
    )


def test_build_stage_specs_includes_optional_model_provider_readiness(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_model_provider_readiness=True)

    deploy_stage = server_delivery_acceptance.build_stage_specs(args)[0]

    assert deploy_stage.command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--check-model-provider-readiness",
        "--model-provider-readiness-json-output",
        str(tmp_path / "model-provider-readiness.json"),
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert deploy_stage.evidence_files == [
        tmp_path / "server-deploy-check.json",
        tmp_path / "model-provider-readiness.json",
    ]


def test_build_stage_specs_model_provider_readiness_is_deploy_only(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        include_systemd_unit_check=True,
        include_model_provider_readiness=True,
        include_alert_telegram_preview=True,
        include_alert_telegram_env_check=True,
        include_alert_telegram_service_verify=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert stages[0].command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--check-systemd-units",
        "--check-model-provider-readiness",
        "--model-provider-readiness-json-output",
        str(tmp_path / "model-provider-readiness.json"),
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert stages[0].evidence_files == [
        tmp_path / "server-deploy-check.json",
        tmp_path / "model-provider-readiness.json",
    ]
    assert all("--check-model-provider-readiness" not in stage.command for stage in stages[1:])
    assert all(
        "--model-provider-readiness-json-output" not in stage.command
        for stage in stages[1:]
    )


def test_build_stage_specs_includes_optional_database_inventory(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_database_inventory=True)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "database_inventory",
        "runtime_check",
    ]
    assert stages[3].command == [
        "python",
        "infra/scripts/database_inventory.py",
        "--json-output",
        str(tmp_path / "database-inventory.json"),
    ]
    assert stages[3].evidence_files == [tmp_path / "database-inventory.json"]


def test_build_stage_specs_database_inventory_is_read_only(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        include_database_inventory=True,
        base_url="https://api.example.test",
    )

    database_stage = server_delivery_acceptance.build_stage_specs(args)[3]

    forbidden_args = {
        "--base-url",
        "--check-backup",
        "--check-json-output",
        "--confirm-restore",
        "--delete",
        "--send",
        "--env-file",
        "--ops-evidence-output",
        "--require-radar-signal-analysis-sample",
        "seed_demo_data.py",
        "server_runtime_check.py",
        "server_deploy_check.py",
        "postgres_backup.py",
        "postgres_restore.py",
        "systemctl",
        "journalctl",
    }
    assert forbidden_args.isdisjoint(database_stage.command)


def test_build_stage_specs_production_readiness_preset_expands_checks(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, production_readiness=True)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "database_inventory",
        "runtime_check",
        "monitor_alert_payload",
        "telegram_alert_preview",
        "telegram_alert_env_check",
    ]
    assert stages[0].command == [
        "python",
        "infra/scripts/server_deploy_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--check-containers",
        "--check-api",
        "--check-m5-smoke",
        "--require-radar-signal-analysis-sample",
        "--check-server-compose-contract",
        "--check-telegram-strict-binding",
        "--check-systemd-units",
        "--check-tushare-anns-d-beat-enablement",
        "--tushare-anns-d-beat-enablement-json-output",
        str(tmp_path / "tushare-anns-d-beat-enablement.json"),
        "--check-model-provider-readiness",
        "--model-provider-readiness-json-output",
        str(tmp_path / "model-provider-readiness.json"),
        "--json-output",
        str(tmp_path / "server-deploy-check.json"),
    ]
    assert stages[0].evidence_files == [
        tmp_path / "server-deploy-check.json",
        tmp_path / "tushare-anns-d-beat-enablement.json",
        tmp_path / "model-provider-readiness.json",
    ]
    assert stages[3].command == [
        "python",
        "infra/scripts/database_inventory.py",
        "--json-output",
        str(tmp_path / "database-inventory.json"),
    ]
    assert "--ops-evidence-output" in stages[4].command
    assert str(tmp_path / "server-ops-evidence.json") in stages[4].command
    assert stages[4].evidence_files == [
        tmp_path / "server-runtime-check.json",
        tmp_path / "server-ops-evidence.json",
    ]
    assert stages[5].command == [
        "python",
        "infra/scripts/server_monitor_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--include-ops-trends",
        "--json-output",
        str(tmp_path / "server-monitor-summary.json"),
        "--alert-json-output",
        str(tmp_path / "server-alert-payload.json"),
    ]
    assert stages[6].command == [
        "python",
        "infra/scripts/server_alert_telegram.py",
        str(tmp_path / "server-alert-payload.json"),
        "--json-output",
        str(tmp_path / "server-alert-telegram-preview.json"),
    ]
    assert stages[7].command == [
        "python",
        "infra/scripts/server_alert_telegram_env_check.py",
        "--env-file",
        "/etc/baizefindb/telegram-alert.env",
        "--json-output",
        str(tmp_path / "server-alert-telegram-env-check.json"),
    ]


def test_build_stage_specs_production_readiness_preset_is_non_destructive(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, production_readiness=True)

    stages = server_delivery_acceptance.build_stage_specs(args)
    stage_names = [stage.name for stage in stages]
    all_command_args = [item for stage in stages for item in stage.command]

    assert "telegram_alert_service_verify" not in stage_names
    forbidden_args = {
        "--send",
        "--telegram-alert-env-strict-permissions",
        "--fail-on-warning",
        "--fail-fast",
        "--confirm-restore",
        "--delete",
        "systemctl",
        "journalctl",
    }
    assert forbidden_args.isdisjoint(all_command_args)
    assert not any("postgres_restore.py" in item for item in all_command_args)


def test_build_stage_specs_production_readiness_composes_with_strict_options(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        production_readiness=True,
        fail_on_warning=True,
        include_alert_telegram_service_verify=True,
        telegram_alert_env_strict_permissions=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "database_inventory",
        "runtime_check",
        "monitor_alert_payload",
        "telegram_alert_preview",
        "telegram_alert_env_check",
        "telegram_alert_service_verify",
    ]
    assert "--fail-on-warning" not in stages[0].command
    assert "--fail-on-warning" not in stages[1].command
    assert "--fail-on-warning" not in stages[2].command
    assert "--fail-on-warning" not in stages[3].command
    assert "--fail-on-warning" in stages[4].command
    assert "--strict-permissions" in stages[7].command
    assert stages[8].command[1] == "infra/scripts/server_alert_telegram_service_verify.py"


def test_build_stage_specs_passes_fail_on_warning_to_runtime_only(tmp_path: Path) -> None:
    args = _args(tmp_path, fail_on_warning=True)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert "--fail-on-warning" not in stages[0].command
    assert "--fail-on-warning" not in stages[1].command
    assert "--fail-on-warning" not in stages[2].command
    assert "--fail-on-warning" in stages[3].command


def test_build_stage_specs_includes_optional_ops_evidence(tmp_path: Path) -> None:
    args = _args(tmp_path, include_ops_evidence=True)

    runtime_stage = server_delivery_acceptance.build_stage_specs(args)[-1]

    assert "--ops-evidence-output" in runtime_stage.command
    assert str(tmp_path / "server-ops-evidence.json") in runtime_stage.command
    assert runtime_stage.evidence_files == [
        tmp_path / "server-runtime-check.json",
        tmp_path / "server-ops-evidence.json",
    ]


def test_build_stage_specs_includes_optional_alert_telegram_preview(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_alert_telegram_preview=True)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "runtime_check",
        "monitor_alert_payload",
        "telegram_alert_preview",
    ]
    assert stages[4].command == [
        "python",
        "infra/scripts/server_monitor_check.py",
        "--base-url",
        "http://127.0.0.1:8000",
        "--include-ops-trends",
        "--json-output",
        str(tmp_path / "server-monitor-summary.json"),
        "--alert-json-output",
        str(tmp_path / "server-alert-payload.json"),
    ]
    assert stages[4].evidence_files == [
        tmp_path / "server-monitor-summary.json",
        tmp_path / "server-alert-payload.json",
    ]
    assert stages[5].command == [
        "python",
        "infra/scripts/server_alert_telegram.py",
        str(tmp_path / "server-alert-payload.json"),
        "--json-output",
        str(tmp_path / "server-alert-telegram-preview.json"),
    ]
    assert "--send" not in stages[5].command
    assert "--dedupe-state" not in stages[5].command
    assert "--ignore-dedupe" not in stages[5].command
    assert stages[5].evidence_files == [
        tmp_path / "server-alert-telegram-preview.json"
    ]


def test_build_stage_specs_includes_optional_alert_telegram_env_check(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_alert_telegram_env_check=True)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "runtime_check",
        "telegram_alert_env_check",
    ]
    assert stages[4].command == [
        "python",
        "infra/scripts/server_alert_telegram_env_check.py",
        "--env-file",
        "/etc/baizefindb/telegram-alert.env",
        "--json-output",
        str(tmp_path / "server-alert-telegram-env-check.json"),
    ]
    assert stages[4].evidence_files == [
        tmp_path / "server-alert-telegram-env-check.json"
    ]


def test_build_stage_specs_places_alert_env_check_after_preview(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        include_alert_telegram_preview=True,
        include_alert_telegram_env_check=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "runtime_check",
        "monitor_alert_payload",
        "telegram_alert_preview",
        "telegram_alert_env_check",
    ]


def test_build_stage_specs_passes_alert_env_file_and_strict_permissions(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "telegram-alert.env"
    args = _args(
        tmp_path,
        include_alert_telegram_env_check=True,
        telegram_alert_env_file=env_file,
        telegram_alert_env_strict_permissions=True,
    )

    env_stage = server_delivery_acceptance.build_stage_specs(args)[-1]

    assert env_stage.command == [
        "python",
        "infra/scripts/server_alert_telegram_env_check.py",
        "--env-file",
        str(env_file),
        "--json-output",
        str(tmp_path / "server-alert-telegram-env-check.json"),
        "--strict-permissions",
    ]


def test_build_stage_specs_alert_env_check_does_not_send_or_pass_secret_args(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_alert_telegram_env_check=True)

    env_stage = server_delivery_acceptance.build_stage_specs(args)[-1]

    forbidden_args = {
        "--send",
        "--dedupe-state",
        "--dedupe-ttl-seconds",
        "--ignore-dedupe",
        "--chat-id",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_CHAT_IDS",
    }
    assert forbidden_args.isdisjoint(env_stage.command)


def test_build_stage_specs_excludes_alert_service_verify_by_default(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert "telegram_alert_service_verify" not in [stage.name for stage in stages]


def test_build_stage_specs_includes_optional_alert_service_verify(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_alert_telegram_service_verify=True)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "runtime_check",
        "telegram_alert_service_verify",
    ]
    assert stages[4].command == [
        "python",
        "infra/scripts/server_alert_telegram_service_verify.py",
        "--env-check-json",
        "evidence/server-alert-telegram-env-check.json",
        "--delivery-json",
        "evidence/server-alert-telegram-send.json",
        "--dedupe-state-json",
        "evidence/server-alert-telegram-dedupe-state.json",
        "--json-output",
        str(tmp_path / "server-alert-telegram-service-verification.json"),
    ]
    assert stages[4].evidence_files == [
        tmp_path / "server-alert-telegram-service-verification.json"
    ]


def test_build_stage_specs_places_alert_service_verify_after_preview_and_env_check(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        include_alert_telegram_preview=True,
        include_alert_telegram_env_check=True,
        include_alert_telegram_service_verify=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "runtime_check",
        "monitor_alert_payload",
        "telegram_alert_preview",
        "telegram_alert_env_check",
        "telegram_alert_service_verify",
    ]


def test_build_stage_specs_passes_custom_alert_service_verify_paths(
    tmp_path: Path,
) -> None:
    env_check = tmp_path / "handoff" / "env-check.json"
    delivery = tmp_path / "handoff" / "send.json"
    dedupe_state = tmp_path / "handoff" / "dedupe-state.json"
    args = _args(
        tmp_path,
        include_alert_telegram_service_verify=True,
        telegram_alert_service_env_check_json=env_check,
        telegram_alert_service_delivery_json=delivery,
        telegram_alert_service_dedupe_state_json=dedupe_state,
    )

    verify_stage = server_delivery_acceptance.build_stage_specs(args)[-1]

    assert verify_stage.command == [
        "python",
        "infra/scripts/server_alert_telegram_service_verify.py",
        "--env-check-json",
        str(env_check),
        "--delivery-json",
        str(delivery),
        "--dedupe-state-json",
        str(dedupe_state),
        "--json-output",
        str(tmp_path / "server-alert-telegram-service-verification.json"),
    ]


def test_build_stage_specs_alert_service_verify_is_read_only(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, include_alert_telegram_service_verify=True)

    verify_stage = server_delivery_acceptance.build_stage_specs(args)[-1]

    forbidden_args = {
        "--send",
        "--chat-id",
        "--env-file",
        "--ignore-dedupe",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_CHAT_IDS",
        "systemctl",
        "journalctl",
        "server_alert_telegram.py",
        "server_alert_telegram_env_check.py",
    }
    assert forbidden_args.isdisjoint(verify_stage.command)


def test_build_stage_specs_passes_base_url_to_alert_preview_monitor(
    tmp_path: Path,
) -> None:
    args = _args(
        tmp_path,
        base_url="https://api.example.test",
        include_alert_telegram_preview=True,
    )

    stages = server_delivery_acceptance.build_stage_specs(args)

    monitor_stage = stages[-2]
    telegram_stage = stages[-1]
    assert "--base-url" in monitor_stage.command
    assert "https://api.example.test" in monitor_stage.command
    assert "--base-url" not in telegram_stage.command
    assert "--send" not in telegram_stage.command


def test_build_stage_specs_supports_runtime_overrides(tmp_path: Path) -> None:
    args = _args(tmp_path, runtime_samples=5, runtime_interval_seconds=7)

    runtime_stage = server_delivery_acceptance.build_stage_specs(args)[-1]

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


def test_build_stage_specs_adds_optional_restore_check_before_runtime(
    tmp_path: Path,
) -> None:
    restore_input = Path("backups/pre-upgrade.sql")
    args = _args(tmp_path, restore_check_input=restore_input)

    stages = server_delivery_acceptance.build_stage_specs(args)

    assert [stage.name for stage in stages] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "restore_check",
        "runtime_check",
    ]
    assert stages[3].command == [
        "python",
        "infra/scripts/postgres_restore.py",
        str(restore_input),
        "--check-only",
        "--check-json-output",
        str(tmp_path / "postgres-restore-check.json"),
    ]
    assert "--confirm-restore" not in stages[3].command
    assert stages[3].evidence_files == [tmp_path / "postgres-restore-check.json"]


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


def test_plan_acceptance_builds_plan_without_running_helpers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    args = _args(tmp_path, production_readiness=True)

    def fail_run_stage(*args, **kwargs):
        raise AssertionError("plan-only must not run helper stages")

    monkeypatch.setattr(server_delivery_acceptance, "run_stage", fail_run_stage)

    results = server_delivery_acceptance.plan_acceptance(args)

    assert [result.name for result in results] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "database_inventory",
        "runtime_check",
        "monitor_alert_payload",
        "telegram_alert_preview",
        "telegram_alert_env_check",
    ]
    assert {result.status for result in results} == {"planned"}
    assert all(result.exit_code is None for result in results)
    assert all(result.stdout == "" and result.stderr == "" for result in results)
    assert "--check-server-compose-contract" in results[0].command
    assert results[3].command[1] == "infra/scripts/database_inventory.py"
    assert "--ops-evidence-output" in results[4].command


def test_plan_acceptance_preserves_skipped_stages(tmp_path: Path) -> None:
    args = _args(
        tmp_path,
        skip_backup_check=True,
        skip_backup_retention=True,
        skip_runtime_check=True,
    )

    results = server_delivery_acceptance.plan_acceptance(args)

    assert [result.name for result in results] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "runtime_check",
    ]
    assert [result.status for result in results] == [
        "planned",
        "skipped",
        "skipped",
        "skipped",
    ]
    assert results[1].command == []
    assert results[2].command == []
    assert results[3].command == []


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


def test_run_stage_promotes_alert_service_verify_warning(
    monkeypatch,
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "server-alert-telegram-service-verification.json"
    evidence.write_text(json.dumps({"status": "warn"}), encoding="utf-8")

    monkeypatch.setattr(
        server_delivery_acceptance.subprocess,
        "run",
        lambda *args, **kwargs: _Completed(returncode=0),
    )

    result = server_delivery_acceptance.run_stage(
        server_delivery_acceptance.StageSpec(
            name="telegram_alert_service_verify",
            command=["python", "infra/scripts/server_alert_telegram_service_verify.py"],
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
    assert report["profile"] == "default"
    assert report["execution_mode"] == "run"
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
    assert report["profile"] == "default"
    assert report["execution_mode"] == "run"
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


def test_build_report_accepts_production_readiness_profile(tmp_path: Path) -> None:
    report = server_delivery_acceptance.build_report(
        [_result("deploy_preflight", "ok", 0)],
        evidence_dir=tmp_path,
        profile="production_readiness",
    )

    assert report["profile"] == "production_readiness"
    assert report["status"] == "ok"


def test_build_report_accepts_plan_execution_mode(tmp_path: Path) -> None:
    report = server_delivery_acceptance.build_report(
        [
            _result("deploy_preflight", "planned", None),
            _result("backup_check", "skipped", None),
        ],
        evidence_dir=tmp_path,
        execution_mode="plan",
    )

    assert report["execution_mode"] == "plan"
    assert report["status"] == "planned"
    assert report["summary"] == {
        "total": 2,
        "ok": 0,
        "warn": 0,
        "fail": 0,
        "skipped": 1,
        "planned": 1,
    }


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
    assert report["profile"] == "default"
    assert report["execution_mode"] == "run"
    assert report["summary"]["fail"] == 1
    assert "profile=default" in captured.out
    assert "execution_mode=run" in captured.out
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
    assert report["profile"] == "default"
    assert report["execution_mode"] == "run"
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
    assert report["profile"] == "default"
    assert report["execution_mode"] == "run"
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


def test_main_production_readiness_writes_profile(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "acceptance.json"

    monkeypatch.setattr(server_delivery_acceptance, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        server_delivery_acceptance,
        "run_stage",
        lambda stage, *, repo_root: server_delivery_acceptance.StageResult(
            name=stage.name,
            status="ok",
            command=stage.command,
            exit_code=0,
            evidence_files=stage.evidence_files,
            evidence_statuses={str(path): "ok" for path in stage.evidence_files},
        ),
    )

    exit_code = server_delivery_acceptance.main(
        [
            "--production-readiness",
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

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["profile"] == "production_readiness"
    assert report["execution_mode"] == "run"
    assert [stage["name"] for stage in report["stages"]] == [
        "deploy_preflight",
        "backup_check",
        "backup_retention",
        "database_inventory",
        "runtime_check",
        "monitor_alert_payload",
        "telegram_alert_preview",
        "telegram_alert_env_check",
    ]


def test_main_plan_only_writes_production_readiness_plan(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "acceptance-plan.json"

    def fail_subprocess_run(*args, **kwargs):
        raise AssertionError("plan-only must not invoke helper subprocesses")

    monkeypatch.setattr(server_delivery_acceptance.subprocess, "run", fail_subprocess_run)

    exit_code = server_delivery_acceptance.main(
        [
            "--plan-only",
            "--production-readiness",
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
    assert report["status"] == "planned"
    assert report["execution_mode"] == "plan"
    assert report["profile"] == "production_readiness"
    assert report["summary"] == {
        "total": 8,
        "ok": 0,
        "warn": 0,
        "fail": 0,
        "skipped": 0,
        "planned": 8,
    }
    assert [stage["status"] for stage in report["stages"]] == ["planned"] * 8
    assert report["stages"][0]["exit_code"] is None
    assert "--check-server-compose-contract" in report["stages"][0]["command"]
    assert "--check-model-provider-readiness" in report["stages"][0]["command"]
    assert str(tmp_path / "evidence" / "model-provider-readiness.json") in report[
        "stages"
    ][0]["evidence_files"]
    assert report["stages"][3]["command"][1] == "infra/scripts/database_inventory.py"
    assert "--ops-evidence-output" in report["stages"][4]["command"]
    assert "profile=production_readiness" in captured.out
    assert "execution_mode=plan" in captured.out
    assert "[PLANNED] deploy_preflight exit=None" in captured.out


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
