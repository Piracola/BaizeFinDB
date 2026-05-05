import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LINUX_DIR = REPO_ROOT / "infra" / "linux"


def test_monitor_service_invokes_compact_monitor_check() -> None:
    service = _read_unit("baizefindb-monitor.service")

    assert service["Unit"]["Requires"] == "baizefindb.service"
    assert "network-online.target" in service["Unit"]["After"]
    assert service["Service"]["Type"] == "oneshot"
    assert service["Service"]["WorkingDirectory"] == "/opt/baizefindb"
    assert service["Service"]["User"] == "baizefindb"
    assert service["Service"]["Group"] == "baizefindb"
    assert service["Service"]["ExecStartPre"] == "/usr/bin/mkdir -p /opt/baizefindb/evidence"

    command = service["Service"]["ExecStart"]
    assert "server_monitor_check.py" in command
    assert "--include-ops-trends" in command
    assert "--json-output ${BAIZEFINDB_MONITOR_OUTPUT}" in command
    assert "--runtime-json-output ${BAIZEFINDB_RUNTIME_OUTPUT}" in command
    assert "--alert-json-output ${BAIZEFINDB_ALERT_OUTPUT}" in command
    assert "--fail-on-warning" not in command

    environment = service["Service"]["Environment"]
    assert "BAIZEFINDB_MONITOR_OUTPUT=evidence/server-monitor-summary.json" in environment
    assert "BAIZEFINDB_RUNTIME_OUTPUT=evidence/server-runtime-monitor.json" in environment
    assert "BAIZEFINDB_ALERT_OUTPUT=evidence/server-alert-payload.json" in environment
    assert ".env" not in environment


def test_monitor_service_does_not_embed_secrets_or_notification_delivery() -> None:
    text = (LINUX_DIR / "baizefindb-monitor.service").read_text(encoding="utf-8").lower()

    forbidden = [
        "telegram_bot_token",
        "telegram_webhook_secret",
        "webhook_url",
        "password",
        "secret",
        "token=",
        "curl ",
        "sendmail",
        "smtp",
    ]
    for marker in forbidden:
        assert marker not in text


def test_monitor_timer_runs_every_five_minutes() -> None:
    timer = _read_unit("baizefindb-monitor.timer")

    assert timer["Timer"]["Unit"] == "baizefindb-monitor.service"
    assert timer["Timer"]["OnBootSec"] == "2min"
    assert timer["Timer"]["OnUnitActiveSec"] == "5min"
    assert timer["Timer"]["AccuracySec"] == "30s"
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"


def test_postgres_backup_service_uses_existing_backup_helper() -> None:
    service = _read_unit("baizefindb-postgres-backup.service")
    text = (LINUX_DIR / "baizefindb-postgres-backup.service").read_text(
        encoding="utf-8"
    )

    assert service["Unit"]["Requires"] == "baizefindb.service"
    assert "baizefindb.service" in service["Unit"]["After"]
    assert "docker.service" in service["Unit"]["After"]
    assert service["Service"]["Type"] == "oneshot"
    assert service["Service"]["WorkingDirectory"] == "/opt/baizefindb"
    assert service["Service"]["User"] == "baizefindb"
    assert service["Service"]["Group"] == "baizefindb"
    assert "/usr/bin/mkdir -p /opt/baizefindb/backups /opt/baizefindb/evidence" in text
    assert "postgres_backup.py --backup-dir backups --check-only" in text
    assert "--check-json-output ${BAIZEFINDB_BACKUP_CHECK_OUTPUT}" in text
    assert "postgres_backup.py --backup-dir backups" in service["Service"]["ExecStart"]
    assert "postgres_restore.py" not in text
    assert "--confirm-restore" not in text


def test_postgres_backup_service_does_not_embed_secrets_or_notifications() -> None:
    text = (LINUX_DIR / "baizefindb-postgres-backup.service").read_text(
        encoding="utf-8"
    ).lower()

    forbidden = [
        "telegram_bot_token",
        "telegram_webhook_secret",
        "webhook_url",
        "password=",
        "secret=",
        "token=",
        "curl ",
        "sendmail",
        "smtp",
    ]
    for marker in forbidden:
        assert marker not in text


def test_postgres_backup_timer_runs_daily_with_jitter() -> None:
    timer = _read_unit("baizefindb-postgres-backup.timer")

    assert timer["Timer"]["Unit"] == "baizefindb-postgres-backup.service"
    assert timer["Timer"]["OnCalendar"] == "*-*-* 03:15:00"
    assert timer["Timer"]["RandomizedDelaySec"] == "15min"
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"


def _read_unit(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    path = LINUX_DIR / name
    assert path.exists()
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return parser
