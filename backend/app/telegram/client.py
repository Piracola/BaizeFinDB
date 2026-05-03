import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_SEND_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class TelegramSendResult:
    ok: bool
    status_code: int | None = None
    error: str | None = None


class TelegramClient:
    def __init__(self, bot_token: str | None) -> None:
        self._bot_token = bot_token.strip() if bot_token else None

    @property
    def configured(self) -> bool:
        return bool(self._bot_token)

    async def send_message(self, chat_id: int, text: str) -> TelegramSendResult:
        if self._bot_token is None:
            return TelegramSendResult(ok=False, error="bot token is not configured")

        return await asyncio.to_thread(self._send_message_sync, chat_id, text)

    def _send_message_sync(self, chat_id: int, text: str) -> TelegramSendResult:
        url = f"{TELEGRAM_API_BASE_URL}/bot{self._bot_token}/sendMessage"
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        ).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=TELEGRAM_SEND_TIMEOUT_SECONDS,
            ) as response:
                body = response.read()
                response_payload = json.loads(body.decode("utf-8")) if body else {}
                ok = bool(response_payload.get("ok"))
                return TelegramSendResult(ok=ok, status_code=response.status)
        except urllib.error.HTTPError as exc:
            return TelegramSendResult(
                ok=False,
                status_code=exc.code,
                error=exc.__class__.__name__,
            )
        except Exception as exc:
            return TelegramSendResult(ok=False, error=exc.__class__.__name__)
