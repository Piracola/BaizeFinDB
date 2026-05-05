import importlib.util
import json
import stat
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "server_alert_telegram_env_check.py"
)
SPEC = importlib.util.spec_from_file_location("server_alert_telegram_env_check", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
server_alert_telegram_env_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_alert_telegram_env_check
SPEC.loader.exec_module(server_alert_telegram_env_check)


def test_evaluate_valid_env_file_masks_secret_values(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path,
        """
        TELEGRAM_ALLOWED_CHAT_IDS=123456789,-987654321
        TELEGRAM_BOT_TOKEN=bot-token-secret
        """,
    )

    report = server_alert_telegram_env_check.evaluate_env_file(env_file)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["report_type"] == "server_alert_telegram_env_check"
    assert report["status"] == "ok"
    assert report["token_configured"] is True
    assert report["chat_id_count"] == 2
    assert report["chat_refs"] == ["telegram-chat-***6789", "telegram-chat--***4321"]
    assert "bot-token-secret" not in encoded
    assert "123456789" not in encoded
    assert "987654321" not in encoded


def test_evaluate_missing_file_fails(tmp_path: Path) -> None:
    report = server_alert_telegram_env_check.evaluate_env_file(tmp_path / "missing.env")

    assert report["status"] == "fail"
    assert report["summary"]["fail"] == 1
    assert report["token_configured"] is False
    assert report["chat_id_count"] == 0


def test_symlink_env_file_fails(tmp_path: Path) -> None:
    target = _write_env(
        tmp_path,
        """
        TELEGRAM_ALLOWED_CHAT_IDS=123456789
        TELEGRAM_BOT_TOKEN=bot-token-secret
        """,
    )
    link = tmp_path / "telegram-alert-link.env"
    link.symlink_to(target)

    report = server_alert_telegram_env_check.evaluate_env_file(link)

    assert report["status"] == "fail"
    assert _check(report, "env file")["detail"] == "env file must not be a symlink"


def test_group_world_permissions_warn_by_default(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path,
        """
        TELEGRAM_ALLOWED_CHAT_IDS=123456789
        TELEGRAM_BOT_TOKEN=bot-token-secret
        """,
        mode=0o644,
    )

    report = server_alert_telegram_env_check.evaluate_env_file(env_file)

    assert report["status"] == "warn"
    assert _check(report, "env file permissions")["status"] == "warn"


def test_group_world_permissions_fail_in_strict_mode(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path,
        """
        TELEGRAM_ALLOWED_CHAT_IDS=123456789
        TELEGRAM_BOT_TOKEN=bot-token-secret
        """,
        mode=0o644,
    )

    report = server_alert_telegram_env_check.evaluate_env_file(
        env_file,
        strict_permissions=True,
    )

    assert report["status"] == "fail"
    assert _check(report, "env file permissions")["status"] == "fail"


def test_malformed_line_fails_without_leaking_contents(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path,
        """
        TELEGRAM_ALLOWED_CHAT_IDS=123456789
        TELEGRAM_BOT_TOKEN=bot-token-secret
        malformed line with bot-token-secret
        """,
    )

    report = server_alert_telegram_env_check.evaluate_env_file(env_file)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "fail"
    assert _check(report, "env syntax")["status"] == "fail"
    assert "bot-token-secret" not in encoded
    assert "malformed line" not in encoded


def test_missing_token_fails(tmp_path: Path) -> None:
    env_file = _write_env(tmp_path, "TELEGRAM_ALLOWED_CHAT_IDS=123456789\n")

    report = server_alert_telegram_env_check.evaluate_env_file(env_file)

    assert report["status"] == "fail"
    assert _check(report, "TELEGRAM_BOT_TOKEN")["status"] == "fail"


def test_invalid_chat_id_fails_without_leaking_raw_value(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path,
        """
        TELEGRAM_ALLOWED_CHAT_IDS=123456789,bad-chat-secret
        TELEGRAM_BOT_TOKEN=bot-token-secret
        """,
    )

    report = server_alert_telegram_env_check.evaluate_env_file(env_file)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "fail"
    assert _check(report, "TELEGRAM_ALLOWED_CHAT_IDS")["status"] == "fail"
    assert "bad-chat-secret" not in encoded
    assert "bot-token-secret" not in encoded


def test_duplicate_chat_ids_are_deduped_and_masked(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path,
        """
        TELEGRAM_ALLOWED_CHAT_IDS=123456789,-987654321,123456789
        TELEGRAM_BOT_TOKEN='bot-token-secret'
        """,
    )

    report = server_alert_telegram_env_check.evaluate_env_file(env_file)

    assert report["status"] == "ok"
    assert report["chat_id_count"] == 2
    assert report["chat_refs"] == ["telegram-chat-***6789", "telegram-chat--***4321"]


def test_main_writes_json_output_without_secret_values(
    tmp_path: Path,
    capsys,
) -> None:
    env_file = _write_env(
        tmp_path,
        """
        TELEGRAM_ALLOWED_CHAT_IDS=123456789
        TELEGRAM_BOT_TOKEN=bot-token-secret
        """,
    )
    output = tmp_path / "evidence" / "telegram-env-check.json"

    exit_code = server_alert_telegram_env_check.main(
        ["--env-file", str(env_file), "--json-output", str(output)]
    )
    captured = capsys.readouterr()
    report = json.loads(output.read_text(encoding="utf-8"))
    encoded = json.dumps(report, ensure_ascii=False)

    assert exit_code == 0
    assert report["status"] == "ok"
    assert "json_output=" in captured.out
    assert "bot-token-secret" not in encoded
    assert "123456789" not in encoded


def _write_env(tmp_path: Path, content: str, *, mode: int = 0o600) -> Path:
    env_file = tmp_path / "telegram-alert.env"
    env_file.write_text(_dedent(content), encoding="utf-8")
    env_file.chmod(mode)
    assert stat.S_IMODE(env_file.stat().st_mode) == mode
    return env_file


def _dedent(content: str) -> str:
    lines = content.strip().splitlines()
    return "\n".join(line.strip() for line in lines) + "\n"


def _check(report: dict[str, object], name: str) -> dict[str, object]:
    checks = report["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check["name"] == name:
            return check
    raise AssertionError(f"missing check: {name}")
