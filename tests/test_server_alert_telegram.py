import importlib.util
import json
import sys
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
    items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "report_type": "server_alert_payload",
        "generated_at": "2026-05-05T00:00:00+00:00",
        "status": "warning",
        "severity": "warning",
        "should_notify": should_notify,
        "dedupe_key": "baizefindb:warning:test",
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


def _run(awaitable):
    return __import__("asyncio").run(awaitable)
