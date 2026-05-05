import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "clients" / "windows" / "run-client.ps1"
FIRST_TRIAL_LAUNCHER = REPO_ROOT / "clients" / "windows" / "first-trial.ps1"


def test_first_trial_launcher_delegates_default_smoke_check_args(tmp_path: Path) -> None:
    result, calls = _run_first_trial_launcher(tmp_path)

    assert result.returncode == 0
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url http://127.0.0.1:8000 "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_first_trial_launcher_delegates_overrides_json_compact_and_strict(
    tmp_path: Path,
) -> None:
    json_output = tmp_path / "first-trial-smoke.json"
    compact_output = tmp_path / "first-trial-smoke-compact.json"

    result, calls = _run_first_trial_launcher(
        tmp_path,
        "-ServerUrl",
        "https://api.example.test",
        "-UserKey",
        "analyst",
        "-SmokeLookbackHours",
        "6",
        "-SmokeJsonOutput",
        str(json_output),
        "-SmokeCompactJsonOutput",
        str(compact_output),
        "-SmokeStrict",
    )

    assert result.returncode == 0
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url https://api.example.test "
            "--user-key analyst --ops-readiness-lookback-hours 6 --json-output "
            f"{json_output} --compact-json-output {compact_output} --fail-on-warning"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_first_trial_launcher_smoke_only_delegates_without_gui(
    tmp_path: Path,
) -> None:
    result, calls = _run_first_trial_launcher(tmp_path, "-SmokeOnly")

    assert result.returncode == 0
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url http://127.0.0.1:8000 "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
    ]


def test_first_trial_launcher_blocks_gui_when_delegated_smoke_check_fails(
    tmp_path: Path,
) -> None:
    result, calls = _run_first_trial_launcher(tmp_path, smoke_exit=7)

    assert result.returncode == 7
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url http://127.0.0.1:8000 "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
    ]


def test_first_trial_launcher_is_thin_run_client_delegator() -> None:
    content = FIRST_TRIAL_LAUNCHER.read_text(encoding="utf-8")

    assert "run-client.ps1" in content
    assert "SmokeCheck" in content
    assert "clients.windows.smoke_check" not in content
    assert "clients.windows.baizefindb_client" not in content


def test_first_trial_launcher_database_inventory_contract_is_static() -> None:
    content = FIRST_TRIAL_LAUNCHER.read_text(encoding="utf-8")

    assert "[string]$DatabaseInventoryJsonOutput" in content
    assert "infra/scripts/database_inventory.py" in content
    assert "-DatabaseInventoryJsonOutput requires -StartDockerBackend" in content
    assert (
        content.index("Invoke-DatabaseInventory -JsonOutput $DatabaseInventoryJsonOutput")
        < content.index("Invoke-DeployCheck `")
    )


def test_first_trial_launcher_start_docker_backend_runs_compose_before_delegation(
    tmp_path: Path,
) -> None:
    with _health_server() as server_url:
        result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat",
    ]
    assert python_calls == [
        (
            f"-m clients.windows.smoke_check --server-url {server_url} "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_first_trial_launcher_start_docker_backend_can_write_deploy_check_json(
    tmp_path: Path,
) -> None:
    deploy_output = tmp_path / "evidence" / "server-deploy-check.json"
    with _health_server() as server_url:
        result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DeployCheckJsonOutput",
            str(deploy_output),
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat",
    ]
    assert python_calls == [
        (
            "infra/scripts/server_deploy_check.py --check-containers --check-api "
            f"--json-output {deploy_output}"
        ),
        (
            f"-m clients.windows.smoke_check --server-url {server_url} "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_first_trial_launcher_start_docker_backend_can_write_database_inventory(
    tmp_path: Path,
) -> None:
    inventory_output = tmp_path / "evidence" / "database-inventory.json"
    with _health_server() as server_url:
        result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DatabaseInventoryJsonOutput",
            str(inventory_output),
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat",
    ]
    assert python_calls == [
        f"infra/scripts/database_inventory.py --json-output {inventory_output}",
        (
            f"-m clients.windows.smoke_check --server-url {server_url} "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_first_trial_launcher_database_inventory_runs_before_deploy_check(
    tmp_path: Path,
) -> None:
    inventory_output = tmp_path / "evidence" / "database-inventory.json"
    deploy_output = tmp_path / "evidence" / "server-deploy-check.json"
    with _health_server() as server_url:
        result, python_calls, _docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DatabaseInventoryJsonOutput",
            str(inventory_output),
            "-DeployCheckJsonOutput",
            str(deploy_output),
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert python_calls == [
        f"infra/scripts/database_inventory.py --json-output {inventory_output}",
        (
            "infra/scripts/server_deploy_check.py --check-containers --check-api "
            f"--json-output {deploy_output}"
        ),
        (
            f"-m clients.windows.smoke_check --server-url {server_url} "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_first_trial_launcher_deploy_check_m5_smoke_appends_server_m5_check(
    tmp_path: Path,
) -> None:
    deploy_output = tmp_path / "evidence" / "server-deploy-check.json"
    with _health_server() as server_url:
        result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DeployCheckJsonOutput",
            str(deploy_output),
            "-DeployCheckM5Smoke",
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat",
    ]
    assert python_calls == [
        (
            "infra/scripts/server_deploy_check.py --check-containers --check-api "
            f"--json-output {deploy_output} --check-m5-smoke"
        ),
        (
            f"-m clients.windows.smoke_check --server-url {server_url} "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_first_trial_launcher_deploy_check_compose_contract_appends_server_check(
    tmp_path: Path,
) -> None:
    deploy_output = tmp_path / "evidence" / "server-deploy-check.json"
    with _health_server() as server_url:
        result, python_calls, _docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DeployCheckJsonOutput",
            str(deploy_output),
            "-DeployCheckServerComposeContract",
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert python_calls == [
        (
            "infra/scripts/server_deploy_check.py --check-containers --check-api "
            f"--json-output {deploy_output} --check-server-compose-contract"
        ),
        (
            f"-m clients.windows.smoke_check --server-url {server_url} "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_first_trial_launcher_deploy_check_backup_evidence_appends_backup_check(
    tmp_path: Path,
) -> None:
    deploy_output = tmp_path / "evidence" / "server-deploy-check.json"
    backup_output = tmp_path / "evidence" / "postgres-backup-check.json"
    with _health_server() as server_url:
        result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DeployCheckJsonOutput",
            str(deploy_output),
            "-DeployCheckBackupJsonOutput",
            str(backup_output),
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat",
    ]
    assert python_calls == [
        (
            "infra/scripts/server_deploy_check.py --check-containers --check-api "
            f"--json-output {deploy_output} --check-backup --backup-check-json-output "
            f"{backup_output}"
        ),
        (
            f"-m clients.windows.smoke_check --server-url {server_url} "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_first_trial_launcher_deploy_check_backup_evidence_composes_with_m5(
    tmp_path: Path,
) -> None:
    deploy_output = tmp_path / "evidence" / "server-deploy-check.json"
    backup_output = tmp_path / "evidence" / "postgres-backup-check.json"
    with _health_server() as server_url:
        result, python_calls, _docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DeployCheckJsonOutput",
            str(deploy_output),
            "-DeployCheckM5Smoke",
            "-DeployCheckBackupJsonOutput",
            str(backup_output),
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert python_calls[0] == (
        "infra/scripts/server_deploy_check.py --check-containers --check-api "
        f"--json-output {deploy_output} --check-m5-smoke --check-backup "
        f"--backup-check-json-output {backup_output}"
    )


def test_first_trial_launcher_deploy_check_compose_contract_composes_with_m5_and_backup(
    tmp_path: Path,
) -> None:
    deploy_output = tmp_path / "evidence" / "server-deploy-check.json"
    backup_output = tmp_path / "evidence" / "postgres-backup-check.json"
    with _health_server() as server_url:
        result, python_calls, _docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DeployCheckJsonOutput",
            str(deploy_output),
            "-DeployCheckServerComposeContract",
            "-DeployCheckM5Smoke",
            "-DeployCheckBackupJsonOutput",
            str(backup_output),
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert python_calls[0] == (
        "infra/scripts/server_deploy_check.py --check-containers --check-api "
        f"--json-output {deploy_output} --check-server-compose-contract "
        f"--check-m5-smoke --check-backup --backup-check-json-output {backup_output}"
    )


def test_first_trial_launcher_deploy_check_json_requires_docker_backend(
    tmp_path: Path,
) -> None:
    result, calls = _run_first_trial_launcher(
        tmp_path,
        "-DeployCheckJsonOutput",
        str(tmp_path / "server-deploy-check.json"),
    )

    assert result.returncode == 2
    assert calls == []
    assert "-DeployCheckJsonOutput requires -StartDockerBackend" in result.stderr


def test_first_trial_launcher_database_inventory_requires_docker_backend(
    tmp_path: Path,
) -> None:
    result, calls = _run_first_trial_launcher(
        tmp_path,
        "-DatabaseInventoryJsonOutput",
        str(tmp_path / "database-inventory.json"),
    )

    assert result.returncode == 2
    assert calls == []
    assert "-DatabaseInventoryJsonOutput requires -StartDockerBackend" in result.stderr


def test_first_trial_launcher_deploy_check_m5_smoke_requires_json_output(
    tmp_path: Path,
) -> None:
    result, calls = _run_first_trial_launcher(tmp_path, "-DeployCheckM5Smoke")

    assert result.returncode == 2
    assert calls == []
    assert "-DeployCheckM5Smoke requires -DeployCheckJsonOutput" in result.stderr


def test_first_trial_launcher_deploy_check_compose_contract_requires_json_output(
    tmp_path: Path,
) -> None:
    result, calls = _run_first_trial_launcher(
        tmp_path,
        "-DeployCheckServerComposeContract",
    )

    assert result.returncode == 2
    assert calls == []
    assert "-DeployCheckServerComposeContract requires -DeployCheckJsonOutput" in result.stderr


def test_first_trial_launcher_deploy_check_backup_evidence_requires_json_output(
    tmp_path: Path,
) -> None:
    result, calls = _run_first_trial_launcher(
        tmp_path,
        "-DeployCheckBackupJsonOutput",
        str(tmp_path / "postgres-backup-check.json"),
    )

    assert result.returncode == 2
    assert calls == []
    assert "-DeployCheckBackupJsonOutput requires -DeployCheckJsonOutput" in result.stderr


def test_first_trial_launcher_deploy_check_failure_blocks_smoke_and_gui(
    tmp_path: Path,
) -> None:
    with _health_server() as server_url:
        result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DeployCheckJsonOutput",
            str(tmp_path / "server-deploy-check.json"),
            "-DeployCheckServerComposeContract",
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
            deploy_check_exit=31,
        )

    assert result.returncode == 31
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat",
    ]
    assert python_calls == [
        (
            "infra/scripts/server_deploy_check.py --check-containers --check-api "
            f"--json-output {tmp_path / 'server-deploy-check.json'} "
            "--check-server-compose-contract"
        ),
    ]


def test_first_trial_launcher_database_inventory_failure_blocks_followup_checks(
    tmp_path: Path,
) -> None:
    inventory_output = tmp_path / "evidence" / "database-inventory.json"
    deploy_output = tmp_path / "evidence" / "server-deploy-check.json"
    with _health_server() as server_url:
        result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-ServerUrl",
            server_url,
            "-DatabaseInventoryJsonOutput",
            str(inventory_output),
            "-DeployCheckJsonOutput",
            str(deploy_output),
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
            database_inventory_exit=37,
        )

    assert result.returncode == 37
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat",
    ]
    assert python_calls == [
        f"infra/scripts/database_inventory.py --json-output {inventory_output}",
    ]


def test_first_trial_launcher_start_docker_backend_smoke_only_runs_compose_before_smoke(
    tmp_path: Path,
) -> None:
    with _health_server() as server_url:
        result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
            tmp_path,
            "-StartDockerBackend",
            "-SmokeOnly",
            "-ServerUrl",
            server_url,
            "-BackendHealthTimeoutSeconds",
            "5",
            "-BackendHealthPollIntervalSeconds",
            "1",
        )

    assert result.returncode == 0, result.stderr
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat",
    ]
    assert python_calls == [
        (
            f"-m clients.windows.smoke_check --server-url {server_url} "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
    ]


def test_first_trial_launcher_start_docker_backend_blocks_gui_on_docker_failure(
    tmp_path: Path,
) -> None:
    result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
        tmp_path,
        "-StartDockerBackend",
        "-BackendHealthTimeoutSeconds",
        "1",
        "-BackendHealthPollIntervalSeconds",
        "1",
        docker_fail_match="run --rm api alembic upgrade head",
        docker_exit=23,
    )

    assert result.returncode == 23
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
    ]
    assert python_calls == []


def test_first_trial_launcher_start_docker_backend_blocks_gui_on_health_timeout(
    tmp_path: Path,
) -> None:
    result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
        tmp_path,
        "-StartDockerBackend",
        "-ServerUrl",
        "http://127.0.0.1:9",
        "-BackendHealthTimeoutSeconds",
        "1",
        "-BackendHealthPollIntervalSeconds",
        "1",
    )

    assert result.returncode == 1
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d postgres redis",
        (
            "compose -f docker-compose.yml -f docker-compose.server.yml run --rm "
            "api alembic upgrade head"
        ),
        "compose -f docker-compose.yml -f docker-compose.server.yml up -d api worker beat",
    ]
    assert python_calls == []


def test_first_trial_launcher_start_docker_backend_blocks_before_migration_on_build_failure(
    tmp_path: Path,
) -> None:
    result, python_calls, docker_calls = _run_first_trial_launcher_with_docker(
        tmp_path,
        "-StartDockerBackend",
        "-BackendHealthTimeoutSeconds",
        "1",
        "-BackendHealthPollIntervalSeconds",
        "1",
        docker_fail_match="build api",
        docker_exit=19,
    )

    assert result.returncode == 19
    assert docker_calls == [
        "compose -f docker-compose.yml -f docker-compose.server.yml build api",
    ]
    assert python_calls == []


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


def test_launcher_smoke_check_passes_server_user_json_compact_and_strict_args(
    tmp_path: Path,
) -> None:
    json_output = tmp_path / "windows-smoke.json"
    compact_output = tmp_path / "windows-smoke-compact.json"

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
        "-SmokeCompactJsonOutput",
        str(compact_output),
        "-SmokeStrict",
    )

    assert result.returncode == 0
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url https://api.example.test "
            "--user-key tester --ops-readiness-lookback-hours 6 --json-output "
            f"{json_output} --compact-json-output {compact_output} --fail-on-warning"
        ),
        "-m clients.windows.baizefindb_client",
    ]


def test_launcher_smoke_only_implies_smoke_check_and_skips_gui(tmp_path: Path) -> None:
    result, calls = _run_launcher(
        tmp_path,
        "-ServerUrl",
        "http://127.0.0.1:8000",
        "-UserKey",
        "default",
        "-SmokeOnly",
    )

    assert result.returncode == 0
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url http://127.0.0.1:8000 "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
    ]


def test_launcher_smoke_check_with_smoke_only_skips_gui(tmp_path: Path) -> None:
    result, calls = _run_launcher(
        tmp_path,
        "-ServerUrl",
        "http://127.0.0.1:8000",
        "-UserKey",
        "default",
        "-SmokeCheck",
        "-SmokeOnly",
    )

    assert result.returncode == 0
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url http://127.0.0.1:8000 "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
    ]


def test_launcher_smoke_only_failure_exits_nonzero_without_gui(tmp_path: Path) -> None:
    result, calls = _run_launcher(
        tmp_path,
        "-ServerUrl",
        "http://127.0.0.1:8000",
        "-UserKey",
        "default",
        "-SmokeOnly",
        smoke_exit=7,
    )

    assert result.returncode == 7
    assert calls == [
        (
            "-m clients.windows.smoke_check --server-url http://127.0.0.1:8000 "
            "--user-key default --ops-readiness-lookback-hours 24"
        ),
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
    return _run_powershell_launcher(
        LAUNCHER,
        tmp_path,
        *args,
        smoke_exit=smoke_exit,
    )


def _run_first_trial_launcher(
    tmp_path: Path,
    *args: str,
    smoke_exit: int = 0,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    return _run_powershell_launcher(
        FIRST_TRIAL_LAUNCHER,
        tmp_path,
        *args,
        smoke_exit=smoke_exit,
    )


def _run_first_trial_launcher_with_docker(
    tmp_path: Path,
    *args: str,
    smoke_exit: int = 0,
    docker_fail_match: str = "",
    docker_exit: int = 11,
    deploy_check_exit: int = 0,
    database_inventory_exit: int = 0,
) -> tuple[subprocess.CompletedProcess[str], list[str], list[str]]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is required for launcher script checks.")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python_calls_file = tmp_path / "python-calls.txt"
    docker_calls_file = tmp_path / "docker-calls.txt"
    _write_fake_python(fake_bin / "python.cmd")
    _write_fake_docker(fake_bin / "docker.cmd")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["BAIZEFINDB_PYTHON_CALLS"] = str(python_calls_file)
    env["BAIZEFINDB_DOCKER_CALLS"] = str(docker_calls_file)
    env["BAIZEFINDB_FAKE_SMOKE_EXIT"] = str(smoke_exit)
    env["BAIZEFINDB_FAKE_GUI_EXIT"] = "0"
    env["BAIZEFINDB_FAKE_DOCKER_FAIL_MATCH"] = docker_fail_match
    env["BAIZEFINDB_FAKE_DOCKER_EXIT"] = str(docker_exit)
    env["BAIZEFINDB_FAKE_DEPLOY_CHECK_EXIT"] = str(deploy_check_exit)
    env["BAIZEFINDB_FAKE_DATABASE_INVENTORY_EXIT"] = str(database_inventory_exit)

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(FIRST_TRIAL_LAUNCHER),
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    python_calls = (
        python_calls_file.read_text(encoding="utf-8").splitlines()
        if python_calls_file.exists()
        else []
    )
    docker_calls = (
        docker_calls_file.read_text(encoding="utf-8").splitlines()
        if docker_calls_file.exists()
        else []
    )
    return result, python_calls, docker_calls


def _run_powershell_launcher(
    launcher: Path,
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
            str(launcher),
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
                "if \"%1\"==\"infra/scripts/database_inventory.py\" "
                "exit /b %BAIZEFINDB_FAKE_DATABASE_INVENTORY_EXIT%",
                "if \"%1\"==\"infra/scripts/server_deploy_check.py\" "
                "exit /b %BAIZEFINDB_FAKE_DEPLOY_CHECK_EXIT%",
                "if \"%1\"==\"-m\" if \"%2\"==\"clients.windows.smoke_check\" "
                "exit /b %BAIZEFINDB_FAKE_SMOKE_EXIT%",
                "if \"%1\"==\"-m\" if \"%2\"==\"clients.windows.baizefindb_client\" "
                "exit /b %BAIZEFINDB_FAKE_GUI_EXIT%",
                "exit /b 0",
            ],
        ),
        encoding="utf-8",
    )


def _write_fake_docker(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "@echo off",
                "echo %*>> \"%BAIZEFINDB_DOCKER_CALLS%\"",
                "if not \"%BAIZEFINDB_FAKE_DOCKER_FAIL_MATCH%\"==\"\" (",
                "  echo %* | findstr /C:\"%BAIZEFINDB_FAKE_DOCKER_FAIL_MATCH%\" >nul",
                "  if not errorlevel 1 exit /b %BAIZEFINDB_FAKE_DOCKER_EXIT%",
                ")",
                "exit /b 0",
            ],
        ),
        encoding="utf-8",
    )


@contextmanager
def _health_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
