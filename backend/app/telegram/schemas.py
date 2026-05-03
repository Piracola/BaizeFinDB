from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    binding_count: int = 0
    active_binding_count: int = 0
    webhook_secret_enabled: bool
    push_enabled: bool


class TelegramWebhookResponse(BaseModel):
    accepted: bool
    authorized: bool
    command: str | None = None
    delivery: Literal["sent", "preview", "skipped", "failed"]
    sent: bool
    preview: str
    error: str | None = None


class TelegramPushStatus(StrEnum):
    SENT = "sent"
    PREVIEW = "preview"
    SKIPPED = "skipped"
    FAILED = "failed"


class TelegramPushRequest(BaseModel):
    chat_ids: list[int] = Field(default_factory=list, max_length=20)
    dry_run: bool = False


class TelegramPushDeliveryRead(BaseModel):
    chat_id: int
    user_key: str
    delivery: TelegramPushStatus
    sent: bool
    preview: str
    push_log_id: int | None = None
    generated_report_ids: list[int] = Field(default_factory=list)
    error: str | None = None


class TelegramPushRunRead(BaseModel):
    source_scan_id: int | None = None
    push_enabled: bool
    dry_run: bool
    recipient_count: int
    included_signal_ids: list[int]
    blocked_signal_ids: list[int]
    needs_human_review_signal_ids: list[int]
    priority_counts: dict[str, int]
    deliveries: list[TelegramPushDeliveryRead]


class TelegramPushLogRead(BaseModel):
    id: int
    user_key: str
    channel: str
    chat_id: int | None = None
    source_kind: str
    source_id: int
    status: TelegramPushStatus
    title: str
    message_text: str
    included_signal_ids: list[int]
    blocked_signal_ids: list[int]
    needs_human_review_signal_ids: list[int]
    delivery_details: dict[str, object]
    created_at: datetime


class TelegramBindingCreate(BaseModel):
    chat_id: int
    user_key: str | None = Field(default=None, min_length=1, max_length=120)
    display_name: str = Field(default="", max_length=160)
    is_allowed: bool = True


class TelegramBindingUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    is_allowed: bool | None = None


class TelegramBindingRead(BaseModel):
    id: int
    chat_id: int
    user_key: str
    display_name: str
    is_allowed: bool
    source: str
    created_at: datetime
    updated_at: datetime
