import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "scripts"
    / "server_alert_telegram_service_verify.py"
)
SPEC = importlib.util.spec_from_file_location("server_alert_telegram_service_verify", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
server_alert_telegram_service_verify = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_alert_telegram_service_verify
SPEC.loader.exec_module(server_alert_telegram_service_verify)


def test_full_sent_evidence_success(tmp_path: Path) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(tmp_path)

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=env_path,
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["report_type"] == "server_alert_telegram_service_verification"
    assert report["status"] == "ok"
    assert report["delivery_mode"] == "send"
    assert report["delivery_status"] == "sent"
    assert report["dedupe_enabled"] is True
    assert report["dedupe_state_updated"] is True
    assert report["dedupe_state_entry_count"] == 1
    assert report["recipient_refs"] == ["telegram-chat-***6789"]


def test_deduped_evidence_success(tmp_path: Path) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(
        tmp_path,
        delivery=_delivery_report(
            status="deduped",
            deliveries=[],
            dedupe={"enabled": True, "decision": "suppressed", "state_updated": False},
        ),
    )

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=env_path,
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["status"] == "ok"
    assert report["delivery_status"] == "deduped"
    assert report["dedupe_state_entry_count"] == 1


def test_skipped_delivery_warns_without_dedupe_state(tmp_path: Path) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(
        tmp_path,
        delivery=_delivery_report(
            status="skipped",
            deliveries=[],
            dedupe={"enabled": False, "decision": "not_notifying", "state_updated": False},
        ),
        write_state=False,
    )

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=env_path,
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["status"] == "warn"
    assert report["summary"]["warn"] >= 1
    assert report["dedupe_state_entry_count"] == 0


def test_missing_env_check_fails(tmp_path: Path) -> None:
    _, delivery_path, state_path = _write_evidence_bundle(tmp_path)

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=tmp_path / "missing-env-check.json",
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["status"] == "fail"
    assert _check(report, "env check evidence")["status"] == "fail"


def test_env_warning_status_fails_service_verification(tmp_path: Path) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(
        tmp_path,
        env=_env_report(status="warn"),
    )

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=env_path,
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["status"] == "fail"
    assert _check(report, "env check status")["status"] == "fail"


@pytest.mark.parametrize("status", ["preview", "config_error", "failed", "state_error"])
def test_non_send_success_delivery_status_fails(tmp_path: Path, status: str) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(
        tmp_path,
        delivery=_delivery_report(
            mode="preview" if status == "preview" else "send",
            status=status,
            deliveries=[],
            dedupe={"enabled": False, "decision": status, "state_updated": False},
        ),
        write_state=False,
    )

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=env_path,
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["status"] == "fail"
    assert _check(report, "delivery status")["status"] == "fail"


def test_sent_delivery_missing_dedupe_state_fails(tmp_path: Path) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(tmp_path, write_state=False)

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=env_path,
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["status"] == "fail"
    assert _check(report, "dedupe state evidence")["status"] == "fail"


def test_sent_delivery_without_state_update_fails(tmp_path: Path) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(
        tmp_path,
        delivery=_delivery_report(
            dedupe={"enabled": True, "decision": "allowed", "state_updated": False},
        ),
    )

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=env_path,
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["status"] == "fail"
    assert _check(report, "delivery dedupe")["status"] == "fail"


def test_invalid_dedupe_state_fails(tmp_path: Path) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(
        tmp_path,
        state={"report_type": "server_alert_telegram_dedupe_state", "entries": {}},
    )

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=env_path,
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["status"] == "fail"
    assert _check(report, "dedupe state entries")["status"] == "fail"


def test_symlink_evidence_fails(tmp_path: Path) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(tmp_path)
    link = tmp_path / "env-link.json"
    link.symlink_to(env_path)

    report = server_alert_telegram_service_verify.verify_service_evidence(
        env_check_json=link,
        delivery_json=delivery_path,
        dedupe_state_json=state_path,
    )

    assert report["status"] == "fail"
    assert _check(report, "env check evidence")["detail"] == "evidence file must not be a symlink"


def test_main_writes_json_output_without_sensitive_values(tmp_path: Path, capsys) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(
        tmp_path,
        env=_env_report(chat_refs=["123456789"], token_configured=True),
        delivery=_delivery_report(
            recipient_refs=["123456789"],
            message_preview="bot-token-secret https://provider.example/raw 123456789",
            reason="authorization=secret-token",
        ),
        state=_dedupe_state(
            entries={
                "raw": {
                    "dedupe_key": "https://provider.example/raw?token=secret-token",
                    "recipient_refs": ["123456789"],
                }
            }
        ),
    )
    output = tmp_path / "evidence" / "service-verification.json"

    exit_code = server_alert_telegram_service_verify.main(
        [
            "--env-check-json",
            str(env_path),
            "--delivery-json",
            str(delivery_path),
            "--dedupe-state-json",
            str(state_path),
            "--json-output",
            str(output),
        ]
    )
    captured = capsys.readouterr()
    report = json.loads(output.read_text(encoding="utf-8"))
    encoded = json.dumps(report, ensure_ascii=False)

    assert exit_code == 0
    assert report["status"] == "ok"
    assert "json_output=" in captured.out
    assert "bot-token-secret" not in encoded
    assert "secret-token" not in encoded
    assert "123456789" not in encoded
    assert "https://" not in encoded
    assert "provider.example" not in encoded


def test_main_returns_zero_for_warning_report(tmp_path: Path) -> None:
    env_path, delivery_path, state_path = _write_evidence_bundle(
        tmp_path,
        delivery=_delivery_report(
            status="skipped",
            deliveries=[],
            dedupe={"enabled": False, "decision": "not_notifying", "state_updated": False},
        ),
        write_state=False,
    )

    exit_code = server_alert_telegram_service_verify.main(
        [
            "--env-check-json",
            str(env_path),
            "--delivery-json",
            str(delivery_path),
            "--dedupe-state-json",
            str(state_path),
        ]
    )

    assert exit_code == 0


def _write_evidence_bundle(
    tmp_path: Path,
    *,
    env: dict[str, object] | None = None,
    delivery: dict[str, object] | None = None,
    state: dict[str, object] | None = None,
    write_state: bool = True,
) -> tuple[Path, Path, Path]:
    env_path = tmp_path / "server-alert-telegram-env-check.json"
    delivery_path = tmp_path / "server-alert-telegram-send.json"
    state_path = tmp_path / "server-alert-telegram-dedupe-state.json"
    _write_json(env_path, env or _env_report())
    _write_json(delivery_path, delivery or _delivery_report())
    if write_state:
        _write_json(state_path, state or _dedupe_state())
    return env_path, delivery_path, state_path


def _env_report(
    *,
    status: str = "ok",
    token_configured: bool = True,
    chat_refs: list[str] | None = None,
) -> dict[str, object]:
    refs = chat_refs if chat_refs is not None else ["telegram-chat-***6789"]
    return {
        "report_type": "server_alert_telegram_env_check",
        "generated_at": "2026-05-05T00:00:00+00:00",
        "status": status,
        "token_configured": token_configured,
        "chat_id_count": len(refs),
        "chat_refs": refs,
        "checks": [],
        "boundary": "no-secret env preflight",
    }


def _delivery_report(
    *,
    mode: str = "send",
    status: str = "sent",
    deliveries: list[dict[str, object]] | None = None,
    dedupe: dict[str, object] | None = None,
    recipient_refs: list[str] | None = None,
    message_preview: str = "bounded preview",
    reason: str = "",
) -> dict[str, object]:
    refs = recipient_refs if recipient_refs is not None else ["telegram-chat-***6789"]
    delivery_results = (
        deliveries
        if deliveries is not None
        else [
            {
                "chat_ref": "telegram-chat-***6789",
                "status": "sent",
                "sent": True,
                "telegram_status_code": 200,
                "error": "",
            }
        ]
    )
    return {
        "report_type": "server_alert_telegram_delivery",
        "generated_at": "2026-05-05T00:01:00+00:00",
        "mode": mode,
        "status": status,
        "reason": reason,
        "source_alert_payload": {
            "status": "warning",
            "severity": "warning",
            "should_notify": True,
            "dedupe_key": "baizefindb:warning:test",
        },
        "recipient_count": len(refs),
        "recipient_refs": refs,
        "message_preview": message_preview,
        "deliveries": delivery_results,
        "dedupe": dedupe
        or {"enabled": True, "decision": "allowed", "state_updated": True},
        "boundary": "delivery evidence",
    }


def _dedupe_state(*, entries: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "report_type": "server_alert_telegram_dedupe_state",
        "updated_at": "2026-05-05T00:02:00+00:00",
        "entries": entries
        or {
            "hash": {
                "dedupe_key": "baizefindb:warning:test",
                "last_sent_at": "2026-05-05T00:02:00+00:00",
                "recipient_refs": ["telegram-chat-***6789"],
                "send_count": 1,
                "last_delivery_status": "sent",
            }
        },
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _check(report: dict[str, object], name: str) -> dict[str, object]:
    checks = report["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check["name"] == name:
            return check
    raise AssertionError(f"missing check: {name}")
