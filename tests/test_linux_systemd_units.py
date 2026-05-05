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


def test_alert_telegram_service_invokes_delivery_adapter_with_dedupe() -> None:
    service = _read_unit("baizefindb-alert-telegram.service")
    text = (LINUX_DIR / "baizefindb-alert-telegram.service").read_text(
        encoding="utf-8"
    )

    assert service["Unit"]["Requires"] == "baizefindb.service"
    assert "network-online.target" in service["Unit"]["After"]
    assert "baizefindb-monitor.service" in service["Unit"]["After"]
    assert service["Service"]["Type"] == "oneshot"
    assert service["Service"]["WorkingDirectory"] == "/opt/baizefindb"
    assert service["Service"]["User"] == "baizefindb"
    assert service["Service"]["Group"] == "baizefindb"
    assert (
        service["Service"]["EnvironmentFile"]
        == "-/etc/baizefindb/telegram-alert.env"
    )
    assert "ExecStartPre=/usr/bin/mkdir -p /opt/baizefindb/evidence" in text

    command = service["Service"]["ExecStart"]
    assert "server_alert_telegram.py ${BAIZEFINDB_ALERT_PAYLOAD}" in command
    assert "--send" in command
    assert "--dedupe-state ${BAIZEFINDB_ALERT_TELEGRAM_DEDUPE_STATE}" in command
    assert "--dedupe-ttl-seconds ${BAIZEFINDB_ALERT_TELEGRAM_TTL_SECONDS}" in command
    assert "--json-output ${BAIZEFINDB_ALERT_TELEGRAM_OUTPUT}" in command
    assert "--ignore-dedupe" not in command

    environment = service["Service"]["Environment"]
    assert "BAIZEFINDB_ALERT_PAYLOAD=evidence/server-alert-payload.json" in environment
    assert (
        "BAIZEFINDB_ALERT_TELEGRAM_OUTPUT=evidence/server-alert-telegram-send.json"
        in environment
    )
    assert (
        "BAIZEFINDB_ALERT_TELEGRAM_DEDUPE_STATE=evidence/"
        "server-alert-telegram-dedupe-state.json"
        in environment
    )
    assert "BAIZEFINDB_ALERT_TELEGRAM_TTL_SECONDS=3600" in environment
    assert (
        "BAIZEFINDB_ALERT_TELEGRAM_ENV_CHECK_OUTPUT=evidence/"
        "server-alert-telegram-env-check.json"
        in environment
    )


def test_alert_telegram_service_runs_env_preflight_before_send() -> None:
    text = (LINUX_DIR / "baizefindb-alert-telegram.service").read_text(
        encoding="utf-8"
    )
    preflight_line = _unit_line_containing(
        text,
        "server_alert_telegram_env_check.py",
    )

    assert "ExecStartPre=" in preflight_line
    assert "--env-file /etc/baizefindb/telegram-alert.env" in preflight_line
    assert "--strict-permissions" in preflight_line
    assert (
        "--json-output ${BAIZEFINDB_ALERT_TELEGRAM_ENV_CHECK_OUTPUT}"
        in preflight_line
    )
    assert "--send" not in preflight_line
    assert "--dedupe-state" not in preflight_line
    assert "--dedupe-ttl-seconds" not in preflight_line
    assert "--ignore-dedupe" not in preflight_line
    assert "--chat-id" not in preflight_line
    assert "TELEGRAM_BOT_TOKEN" not in preflight_line
    assert "TELEGRAM_ALLOWED_CHAT_IDS" not in preflight_line


def test_alert_telegram_service_has_no_timer() -> None:
    assert not (LINUX_DIR / "baizefindb-alert-telegram.timer").exists()


def test_alert_telegram_service_does_not_embed_secrets_or_other_delivery() -> None:
    text = (LINUX_DIR / "baizefindb-alert-telegram.service").read_text(
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
        "postgres_backup.py",
        "server_monitor_check.py",
        "run_radar_scan",
    ]
    for marker in forbidden:
        assert marker not in text


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


def _unit_line_containing(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line
    raise AssertionError(f"missing line containing: {needle}")
