from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.telegram.client import TelegramClient
from app.telegram.schemas import TelegramStatusRead, TelegramUpdate, TelegramWebhookResponse
from app.telegram.service import TelegramCommandService, telegram_status

router = APIRouter(prefix="/telegram", tags=["telegram"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
TelegramSecretHeader = Annotated[
    str | None,
    Header(alias="X-Telegram-Bot-Api-Secret-Token"),
]


@router.get("/status", response_model=TelegramStatusRead)
async def status_read() -> TelegramStatusRead:
    return telegram_status(get_settings())


@router.post("/webhook", response_model=TelegramWebhookResponse)
async def webhook(
    update: TelegramUpdate,
    session: SessionDep,
    secret_token: TelegramSecretHeader = None,
) -> TelegramWebhookResponse:
    settings = get_settings()
    expected_secret = (
        settings.telegram_webhook_secret.strip()
        if settings.telegram_webhook_secret
        else None
    )
    if expected_secret and secret_token != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid Telegram webhook secret",
        )

    service = TelegramCommandService(
        settings=settings,
        client=TelegramClient(settings.telegram_bot_token),
    )
    return await service.handle_update(session, update)
