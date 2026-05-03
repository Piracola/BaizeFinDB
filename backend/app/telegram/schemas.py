from typing import Literal

from pydantic import BaseModel, ConfigDict


class TelegramChat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int


class TelegramMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: int | None = None
    chat: TelegramChat
    text: str | None = None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_id: int | None = None
    message: TelegramMessage | None = None


class TelegramStatusRead(BaseModel):
    bot_token_configured: bool
    allowed_chat_count: int
    webhook_secret_enabled: bool


class TelegramWebhookResponse(BaseModel):
    accepted: bool
    authorized: bool
    command: str | None = None
    delivery: Literal["sent", "preview", "skipped", "failed"]
    sent: bool
    preview: str
    error: str | None = None
