from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.portfolio_models import UserProfile
from app.db.telegram_models import TelegramBinding
from app.portfolio.service import get_or_create_user
from app.telegram.schemas import (
    TelegramBindingCreate,
    TelegramBindingRead,
    TelegramBindingUpdate,
)


async def telegram_binding_counts(session: AsyncSession) -> tuple[int, int]:
    total_statement = select(func.count()).select_from(TelegramBinding)
    active_statement = select(func.count()).select_from(TelegramBinding).where(
        TelegramBinding.is_allowed.is_(True),
    )
    total = await session.scalar(total_statement)
    active = await session.scalar(active_statement)
    return int(total or 0), int(active or 0)


async def list_telegram_bindings(
    session: AsyncSession,
    limit: int = 50,
) -> list[TelegramBindingRead]:
    statement = (
        select(TelegramBinding, UserProfile.user_key)
        .join(UserProfile, TelegramBinding.user_id == UserProfile.id)
        .order_by(desc(TelegramBinding.updated_at), desc(TelegramBinding.id))
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return [_binding_read(binding, user_key) for binding, user_key in rows]


async def upsert_telegram_binding(
    session: AsyncSession,
    payload: TelegramBindingCreate,
    *,
    source: str = "manual",
) -> TelegramBindingRead:
    user_key = payload.user_key or _telegram_user_key(payload.chat_id)
    user = await get_or_create_user(session, user_key)
    binding = await get_telegram_binding_model(session, payload.chat_id)

    if binding is None:
        binding = TelegramBinding(
            user_id=user.id,
            chat_id=payload.chat_id,
            display_name=payload.display_name.strip(),
            is_allowed=payload.is_allowed,
            source=source,
        )
        session.add(binding)
    else:
        binding.user_id = user.id
        binding.display_name = payload.display_name.strip()
        binding.is_allowed = payload.is_allowed
        binding.source = source

    await session.commit()
    await session.refresh(binding)
    return _binding_read(binding, user.user_key)


async def update_telegram_binding(
    session: AsyncSession,
    chat_id: int,
    payload: TelegramBindingUpdate,
) -> TelegramBindingRead | None:
    binding = await get_telegram_binding_model(session, chat_id)
    if binding is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    if "display_name" in update_data and update_data["display_name"] is not None:
        binding.display_name = update_data["display_name"].strip()
    if "is_allowed" in update_data and update_data["is_allowed"] is not None:
        binding.is_allowed = update_data["is_allowed"]

    await session.commit()
    await session.refresh(binding)
    user_key = await _user_key_for_binding(session, binding)
    return _binding_read(binding, user_key)


async def get_telegram_binding_model(
    session: AsyncSession,
    chat_id: int,
) -> TelegramBinding | None:
    statement = select(TelegramBinding).where(TelegramBinding.chat_id == chat_id)
    return await session.scalar(statement)


async def resolve_telegram_recipients(
    session: AsyncSession,
    settings: Settings,
    chat_ids: list[int] | None,
) -> list[int]:
    if chat_ids:
        candidates = sorted(set(chat_ids))
    else:
        env_chat_ids = _env_chat_ids(settings)
        candidates = env_chat_ids or await _active_binding_chat_ids(session)

    recipients = [
        chat_id
        for chat_id in candidates
        if await is_telegram_chat_authorized(session, settings, chat_id)
    ]
    return sorted(set(recipients))


async def is_telegram_chat_authorized(
    session: AsyncSession,
    settings: Settings,
    chat_id: int,
) -> bool:
    env_allowed_chat_ids = settings.telegram_allowed_chat_id_set
    if env_allowed_chat_ids and str(chat_id) not in env_allowed_chat_ids:
        return False

    binding = await get_telegram_binding_model(session, chat_id)
    if binding is not None:
        return binding.is_allowed

    if env_allowed_chat_ids:
        return True

    total_count, _ = await telegram_binding_counts(session)
    return total_count == 0


async def _active_binding_chat_ids(session: AsyncSession) -> list[int]:
    statement = (
        select(TelegramBinding.chat_id)
        .where(TelegramBinding.is_allowed.is_(True))
        .order_by(TelegramBinding.chat_id)
    )
    return [int(chat_id) for chat_id in (await session.scalars(statement)).all()]


async def _user_key_for_binding(session: AsyncSession, binding: TelegramBinding) -> str:
    statement = select(UserProfile.user_key).where(UserProfile.id == binding.user_id)
    user_key = await session.scalar(statement)
    return user_key or _telegram_user_key(binding.chat_id)


def _binding_read(binding: TelegramBinding, user_key: str) -> TelegramBindingRead:
    return TelegramBindingRead(
        id=binding.id,
        chat_id=binding.chat_id,
        user_key=user_key,
        display_name=binding.display_name,
        is_allowed=binding.is_allowed,
        source=binding.source,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


def _env_chat_ids(settings: Settings) -> list[int]:
    chat_ids: list[int] = []
    for value in settings.telegram_allowed_chat_id_set:
        try:
            chat_ids.append(int(value))
        except ValueError:
            continue
    return sorted(set(chat_ids))


def _telegram_user_key(chat_id: int) -> str:
    return f"telegram-{chat_id}"
