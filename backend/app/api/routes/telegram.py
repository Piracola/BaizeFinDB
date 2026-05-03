from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.portfolio.schemas import DEFAULT_USER_KEY
from app.telegram.binding_service import (
    list_telegram_bindings,
    telegram_binding_counts,
    update_telegram_binding,
    upsert_telegram_binding,
)
from app.telegram.client import TelegramClient
from app.telegram.push_service import list_telegram_push_logs, send_latest_radar_push
from app.telegram.schemas import (
    TelegramBindingCreate,
    TelegramBindingRead,
    TelegramBindingUpdate,
    TelegramPushLogRead,
    TelegramPushRequest,
    TelegramPushRunRead,
    TelegramStatusRead,
    TelegramUpdate,
    TelegramWebhookResponse,
)
from app.telegram.service import TelegramCommandService, telegram_status

router = APIRouter(prefix="/telegram", tags=["telegram"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]
UserKeyQuery = Annotated[
    str,
    Query(
        min_length=1,
        max_length=120,
        description="Single-user MVP isolation key",
    ),
]
TelegramSecretHeader = Annotated[
    str | None,
    Header(alias="X-Telegram-Bot-Api-Secret-Token"),
]


@router.get("/status", response_model=TelegramStatusRead)
async def status_read(session: SessionDep) -> TelegramStatusRead:
    try:
        binding_count, active_binding_count = await telegram_binding_counts(session)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading Telegram binding status", exc) from exc

    return telegram_status(
        get_settings(),
        binding_count=binding_count,
        active_binding_count=active_binding_count,
    )


@router.post("/webhook", response_model=TelegramWebhookResponse)
async def webhook(
    update: TelegramUpdate,
    session: SessionDep,
    secret_token: TelegramSecretHeader = None,
) -> TelegramWebhookResponse:
    settings = get_settings()
    _validate_secret(settings.telegram_webhook_secret, secret_token)

    service = TelegramCommandService(
        settings=settings,
        client=TelegramClient(settings.telegram_bot_token),
    )
    return await service.handle_update(session, update)


@router.post("/push/latest", response_model=TelegramPushRunRead)
async def push_latest_radar(
    payload: TelegramPushRequest,
    session: SessionDep,
    secret_token: TelegramSecretHeader = None,
) -> TelegramPushRunRead:
    settings = get_settings()
    _validate_secret(settings.telegram_webhook_secret, secret_token)

    try:
        return await send_latest_radar_push(
            session=session,
            settings=settings,
            client=TelegramClient(settings.telegram_bot_token),
            chat_ids=payload.chat_ids or None,
            dry_run=payload.dry_run,
            respect_enabled=False,
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable("sending Telegram radar push", exc) from exc


@router.get("/push/logs", response_model=list[TelegramPushLogRead])
async def push_logs(
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
    limit: LimitQuery = 50,
) -> list[TelegramPushLogRead]:
    try:
        return await list_telegram_push_logs(session, user_key=user_key, limit=limit)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading Telegram push logs", exc) from exc


@router.get("/bindings", response_model=list[TelegramBindingRead])
async def bindings(
    session: SessionDep,
    secret_token: TelegramSecretHeader = None,
    limit: LimitQuery = 50,
) -> list[TelegramBindingRead]:
    settings = get_settings()
    _validate_secret(settings.telegram_webhook_secret, secret_token)

    try:
        return await list_telegram_bindings(session, limit=limit)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading Telegram bindings", exc) from exc


@router.post("/bindings", response_model=TelegramBindingRead)
async def bind_chat(
    payload: TelegramBindingCreate,
    session: SessionDep,
    secret_token: TelegramSecretHeader = None,
) -> TelegramBindingRead:
    settings = get_settings()
    _validate_secret(settings.telegram_webhook_secret, secret_token)

    try:
        return await upsert_telegram_binding(session, payload)
    except SQLAlchemyError as exc:
        raise _database_unavailable("upserting Telegram binding", exc) from exc


@router.patch("/bindings/{chat_id}", response_model=TelegramBindingRead)
async def patch_binding(
    chat_id: int,
    payload: TelegramBindingUpdate,
    session: SessionDep,
    secret_token: TelegramSecretHeader = None,
) -> TelegramBindingRead:
    settings = get_settings()
    _validate_secret(settings.telegram_webhook_secret, secret_token)

    try:
        binding = await update_telegram_binding(session, chat_id, payload)
    except SQLAlchemyError as exc:
        raise _database_unavailable("updating Telegram binding", exc) from exc

    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Telegram binding not found: {chat_id}",
        )

    return binding


def _validate_secret(expected_secret_raw: str | None, secret_token: str | None) -> None:
    expected_secret = expected_secret_raw.strip() if expected_secret_raw else None
    if expected_secret and secret_token != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid Telegram webhook secret",
        )


def _database_unavailable(action: str, exc: SQLAlchemyError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"database unavailable while {action}: {exc.__class__.__name__}",
    )
