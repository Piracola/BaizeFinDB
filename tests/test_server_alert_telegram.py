import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "infra" / "scripts" / "server_alert_telegram.py"
)
SPEC = importlib.util.spec_from_file_location("server_alert_telegram", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
server_alert_telegram = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_alert_telegram
SPEC.loader.exec_module(server_alert_telegram)


def test_format_telegram_message_sanitizes_and_bounds_text() -> None:
    payload = _alert_payload(
        items=[
            {
                "severity": "critical",
                "kind": "failure",
                "endpoint": "ops_readiness",
                "detail": "token=secret-token https://provider.example.test/raw " + "x" * 400,
            }
        ]
    )

    message = server_alert_telegram.format_telegram_message(payload)

    assert "secret-token" not in message
    assert "https://" not in message
    assert "provider.example.test" not in message
    assert "ops_readiness" in message
    assert len(message) <= server_alert_telegram.MAX_TELEGRAM_MESSAGE_LENGTH + 14


def test_resolve_chat_ids_prefers_cli_and_masks_chat_refs() -> None:
    chat_ids = server_alert_telegram.resolve_chat_ids(["1001,-2002,1001"], "9999")

    assert chat_ids == [1001, -2002]
    assert server_alert_telegram.mask_chat_id(1001) == "telegram-chat-***1001"
    assert server_alert_telegram.mask_chat_id(-987654321) == "telegram-chat--***4321"


def test_resolve_chat_ids_rejects_invalid_value() -> None:
    try:
        server_alert_telegram.resolve_chat_ids(["not-a-chat"], None)
    except server_alert_telegram.TelegramAlertInputError as exc:
        assert "invalid Telegram chat id" in str(exc)
    else:
        raise AssertionError("expected invalid chat id to fail")


def test_run_delivery_skips_when_payload_should_not_notify() -> None:
    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(should_notify=False),
            chat_ids=[1001],
            bot_token=None,
            send=True,
        )
    )

    assert exit_code == 0
    assert report["status"] == "skipped"
    assert report["deliveries"] == []
    assert report["source_alert_payload"]["should_notify"] is False


def test_run_delivery_previews_without_sending() -> None:
    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token=None,
            send=False,
        )
    )

    assert exit_code == 0
    assert report["report_type"] == "server_alert_telegram_delivery"
    assert report["generated_at"]
    assert report["mode"] == "preview"
    assert report["status"] == "preview"
    assert report["recipient_refs"] == ["telegram-chat-***1001"]
    assert report["deliveries"] == [
        {
            "chat_ref": "telegram-chat-***1001",
            "status": "preview",
            "sent": False,
            "error": "",
        }
    ]
    assert "bot-token" not in json.dumps(report)


def test_run_delivery_requires_token_and_recipients_for_send() -> None:
    missing_token_report, missing_token_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token=None,
            send=True,
        )
    )
    missing_chat_report, missing_chat_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[],
            bot_token="bot-token",
            send=True,
        )
    )

    assert missing_token_code == 2
    assert missing_token_report["status"] == "config_error"
    assert missing_chat_code == 2
    assert missing_chat_report["status"] == "config_error"


def test_run_delivery_sends_with_existing_client() -> None:
    client = FakeTelegramClient(
        [server_alert_telegram.TelegramSendResult(ok=True, status_code=200)]
    )

    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token="bot-token",
            send=True,
            client=client,
        )
    )

    assert exit_code == 0
    assert report["status"] == "sent"
    assert report["deliveries"][0]["sent"] is True
    assert client.calls[0][0] == 1001
    assert "BaizeFinDB server warning" in client.calls[0][1]


def test_run_delivery_updates_dedupe_state_after_success(tmp_path: Path) -> None:
    client = FakeTelegramClient(
        [server_alert_telegram.TelegramSendResult(ok=True, status_code=200)]
    )
    state_path = tmp_path / "dedupe.json"
    now = datetime(2026, 5, 5, 1, 0, tzinfo=UTC)

    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token="bot-token",
            send=True,
            client=client,
            dedupe_state_path=state_path,
            now=now,
        )
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    entry = state["entries"][server_alert_telegram.dedupe_entry_key("baizefindb:warning:test")]

    assert exit_code == 0
    assert report["status"] == "sent"
    assert report["dedupe"]["decision"] == "allowed"
    assert report["dedupe"]["state_updated"] is True
    assert entry["last_sent_at"] == now.isoformat()
    assert entry["recipient_refs"] == ["telegram-chat-***1001"]
    assert entry["send_count"] == 1


def test_run_delivery_suppresses_duplicate_within_ttl(tmp_path: Path) -> None:
    state_path = tmp_path / "dedupe.json"
    now = datetime(2026, 5, 5, 1, 0, tzinfo=UTC)
    _write_dedupe_state(state_path, "baizefindb:warning:test", now - timedelta(minutes=10))
    client = FakeTelegramClient(
        [server_alert_telegram.TelegramSendResult(ok=True, status_code=200)]
    )

    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token="bot-token",
            send=True,
            client=client,
            dedupe_state_path=state_path,
            dedupe_ttl_seconds=3600,
            now=now,
        )
    )

    assert exit_code == 0
    assert report["status"] == "deduped"
    assert report["dedupe"]["decision"] == "suppressed"
    assert report["dedupe"]["matched_entry"]["age_seconds"] == 600
    assert client.calls == []


def test_run_delivery_resends_after_ttl_and_increments_state(tmp_path: Path) -> None:
    state_path = tmp_path / "dedupe.json"
    now = datetime(2026, 5, 5, 1, 0, tzinfo=UTC)
    _write_dedupe_state(state_path, "baizefindb:warning:test", now - timedelta(hours=2))
    client = FakeTelegramClient(
        [server_alert_telegram.TelegramSendResult(ok=True, status_code=200)]
    )

    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token="bot-token",
            send=True,
            client=client,
            dedupe_state_path=state_path,
            dedupe_ttl_seconds=3600,
            now=now,
        )
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    entry = state["entries"][server_alert_telegram.dedupe_entry_key("baizefindb:warning:test")]

    assert exit_code == 0
    assert report["status"] == "sent"
    assert report["dedupe"]["decision"] == "allowed"
    assert entry["send_count"] == 2
    assert client.calls


def test_run_delivery_ignore_dedupe_sends_and_updates_state(tmp_path: Path) -> None:
    state_path = tmp_path / "dedupe.json"
    now = datetime(2026, 5, 5, 1, 0, tzinfo=UTC)
    _write_dedupe_state(state_path, "baizefindb:warning:test", now - timedelta(minutes=1))
    client = FakeTelegramClient(
        [server_alert_telegram.TelegramSendResult(ok=True, status_code=200)]
    )

    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token="bot-token",
            send=True,
            client=client,
            dedupe_state_path=state_path,
            ignore_dedupe=True,
            now=now,
        )
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    entry = state["entries"][server_alert_telegram.dedupe_entry_key("baizefindb:warning:test")]

    assert exit_code == 0
    assert report["status"] == "sent"
    assert report["dedupe"]["decision"] == "ignored"
    assert entry["send_count"] == 2
    assert client.calls


def test_run_delivery_preview_does_not_create_dedupe_state(tmp_path: Path) -> None:
    state_path = tmp_path / "dedupe.json"

    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token=None,
            send=False,
            dedupe_state_path=state_path,
        )
    )

    assert exit_code == 0
    assert report["status"] == "preview"
    assert report["dedupe"]["decision"] == "preview"
    assert not state_path.exists()


def test_run_delivery_returns_failure_for_failed_send() -> None:
    client = FakeTelegramClient(
        [server_alert_telegram.TelegramSendResult(ok=False, status_code=500, error="HTTPError")]
    )

    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token="bot-token",
            send=True,
            client=client,
        )
    )

    assert exit_code == 1
    assert report["status"] == "failed"
    assert report["deliveries"][0]["status"] == "failed"
    assert report["deliveries"][0]["error"] == "HTTPError"


def test_run_delivery_failed_send_does_not_create_dedupe_state(tmp_path: Path) -> None:
    client = FakeTelegramClient(
        [server_alert_telegram.TelegramSendResult(ok=False, status_code=500, error="HTTPError")]
    )
    state_path = tmp_path / "dedupe.json"

    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            _alert_payload(),
            chat_ids=[1001],
            bot_token="bot-token",
            send=True,
            client=client,
            dedupe_state_path=state_path,
        )
    )

    assert exit_code == 1
    assert report["status"] == "failed"
    assert not state_path.exists()


def test_main_writes_preview_report_from_env_recipients(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "alert.json"
    output_path = tmp_path / "delivery.json"
    input_path.write_text(json.dumps(_alert_payload()), encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001,1002")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token-secret")

    exit_code = server_alert_telegram.main(
        [str(input_path), "--json-output", str(output_path)]
    )
    captured = capsys.readouterr()
    report = json.loads(output_path.read_text(encoding="utf-8"))
    encoded = json.dumps(report, ensure_ascii=False)

    assert exit_code == 0
    assert report["status"] == "preview"
    assert report["recipient_count"] == 2
    assert "bot-token-secret" not in encoded
    assert "json_output=" in captured.out


def test_main_rejects_invalid_dedupe_state_before_sending(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "alert.json"
    state_path = tmp_path / "dedupe.json"
    output_path = tmp_path / "delivery.json"
    input_path.write_text(json.dumps(_alert_payload()), encoding="utf-8")
    state_path.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token-secret")

    exit_code = server_alert_telegram.main(
        [
            str(input_path),
            "--send",
            "--dedupe-state",
            str(state_path),
            "--json-output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert not output_path.exists()


def test_dedupe_state_and_evidence_redact_secret_like_values(tmp_path: Path) -> None:
    state_path = tmp_path / "dedupe.json"
    payload = _alert_payload(
        dedupe_key="https://provider.example/raw?token=secret-token",
    )
    client = FakeTelegramClient(
        [server_alert_telegram.TelegramSendResult(ok=True, status_code=200)]
    )

    report, exit_code = _run(
        server_alert_telegram.run_delivery(
            payload,
            chat_ids=[123456789],
            bot_token="bot-token",
            send=True,
            client=client,
            dedupe_state_path=state_path,
        )
    )
    encoded_report = json.dumps(report, ensure_ascii=False)
    encoded_state = state_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert "secret-token" not in encoded_report
    assert "secret-token" not in encoded_state
    assert "https://" not in encoded_report
    assert "https://" not in encoded_state
    assert "123456789" not in encoded_report
    assert "123456789" not in encoded_state


def test_main_rejects_invalid_payload_without_writing_output(tmp_path: Path) -> None:
    input_path = tmp_path / "alert.json"
    output_path = tmp_path / "delivery.json"
    input_path.write_text('{"report_type":"wrong"}', encoding="utf-8")

    exit_code = server_alert_telegram.main(
        [str(input_path), "--json-output", str(output_path)]
    )

    assert exit_code == 2
    assert not output_path.exists()


class FakeTelegramClient:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def send_message(self, chat_id: int, text: str):
        self.calls.append((chat_id, text))
        return self.results.pop(0)


def _alert_payload(
    *,
    should_notify: bool = True,
    dedupe_key: str = "baizefindb:warning:test",
    items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "report_type": "server_alert_payload",
        "generated_at": "2026-05-05T00:00:00+00:00",
        "status": "warning",
        "severity": "warning",
        "should_notify": should_notify,
        "dedupe_key": dedupe_key,
        "title": "BaizeFinDB server warning",
        "message": "status=warning severity=warning runtime_status=ok failures=0 warnings=1",
        "summary": {
            "runtime_status": "ok",
            "failure_count": 0,
            "warning_count": 1,
        },
        "items": items or [],
        "boundary": "no-send alert payload",
    }


def _write_dedupe_state(path: Path, dedupe_key: str, last_sent_at: datetime) -> None:
    path.write_text(
        json.dumps(
            {
                "report_type": "server_alert_telegram_dedupe_state",
                "updated_at": last_sent_at.isoformat(),
                "entries": {
                    server_alert_telegram.dedupe_entry_key(dedupe_key): {
                        "dedupe_key": dedupe_key,
                        "last_sent_at": last_sent_at.isoformat(),
                        "status": "warning",
                        "severity": "warning",
                        "recipient_refs": ["telegram-chat-***1001"],
                        "send_count": 1,
                        "last_delivery_status": "sent",
                        "delivery_count": 1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _run(awaitable):
    return __import__("asyncio").run(awaitable)
