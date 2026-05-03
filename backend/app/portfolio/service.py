from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.portfolio_models import PortfolioHolding, UserProfile, WatchlistItem
from app.portfolio.schemas import (
    DEFAULT_USER_KEY,
    HoldingCreate,
    HoldingRead,
    HoldingUpdate,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistItemUpdate,
)


class DuplicatePortfolioItemError(ValueError):
    pass


async def get_or_create_user(
    session: AsyncSession,
    user_key: str = DEFAULT_USER_KEY,
) -> UserProfile:
    normalized_user_key = _normalize_user_key(user_key)
    user = await _get_user(session, normalized_user_key)
    if user is not None:
        return user

    user = UserProfile(user_key=normalized_user_key, display_name=normalized_user_key)
    session.add(user)
    await session.flush()
    await session.commit()
    return user


async def list_holdings(
    session: AsyncSession,
    user_key: str = DEFAULT_USER_KEY,
) -> list[HoldingRead]:
    user = await get_or_create_user(session, user_key)
    statement = (
        select(PortfolioHolding)
        .where(PortfolioHolding.user_id == user.id)
        .order_by(desc(PortfolioHolding.updated_at), desc(PortfolioHolding.id))
    )
    holdings = (await session.scalars(statement)).all()
    return [_holding_read(holding, user.user_key) for holding in holdings]


async def create_holding(
    session: AsyncSession,
    payload: HoldingCreate,
    user_key: str = DEFAULT_USER_KEY,
) -> HoldingRead:
    user = await get_or_create_user(session, user_key)
    existing = await _find_holding(
        session,
        user.id,
        payload.market,
        payload.instrument_code,
    )
    if existing is not None:
        raise DuplicatePortfolioItemError("holding already exists")

    holding = PortfolioHolding(
        user_id=user.id,
        instrument_code=payload.instrument_code,
        instrument_name=payload.instrument_name,
        market=payload.market,
        note=payload.note,
        cost_price=payload.cost_price,
        position_ratio=payload.position_ratio,
        alert_enabled=payload.alert_enabled,
    )
    session.add(holding)
    await session.flush()
    await session.commit()
    await session.refresh(holding)
    return _holding_read(holding, user.user_key)


async def update_holding(
    session: AsyncSession,
    holding_id: int,
    payload: HoldingUpdate,
    user_key: str = DEFAULT_USER_KEY,
) -> HoldingRead | None:
    user = await get_or_create_user(session, user_key)
    holding = await _get_holding(session, user.id, holding_id)
    if holding is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(holding, field_name, value)

    await session.commit()
    await session.refresh(holding)
    return _holding_read(holding, user.user_key)


async def delete_holding(
    session: AsyncSession,
    holding_id: int,
    user_key: str = DEFAULT_USER_KEY,
) -> bool:
    user = await get_or_create_user(session, user_key)
    holding = await _get_holding(session, user.id, holding_id)
    if holding is None:
        return False

    await session.delete(holding)
    await session.commit()
    return True


async def list_watchlist_items(
    session: AsyncSession,
    user_key: str = DEFAULT_USER_KEY,
) -> list[WatchlistItemRead]:
    user = await get_or_create_user(session, user_key)
    statement = (
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user.id)
        .order_by(desc(WatchlistItem.updated_at), desc(WatchlistItem.id))
    )
    items = (await session.scalars(statement)).all()
    return [_watchlist_read(item, user.user_key) for item in items]


async def create_watchlist_item(
    session: AsyncSession,
    payload: WatchlistItemCreate,
    user_key: str = DEFAULT_USER_KEY,
) -> WatchlistItemRead:
    user = await get_or_create_user(session, user_key)
    existing = await _find_watchlist_item(
        session,
        user.id,
        payload.market,
        payload.instrument_code,
    )
    if existing is not None:
        raise DuplicatePortfolioItemError("watchlist item already exists")

    item = WatchlistItem(
        user_id=user.id,
        instrument_code=payload.instrument_code,
        instrument_name=payload.instrument_name,
        market=payload.market,
        note=payload.note,
        alert_enabled=payload.alert_enabled,
    )
    session.add(item)
    await session.flush()
    await session.commit()
    await session.refresh(item)
    return _watchlist_read(item, user.user_key)


async def update_watchlist_item(
    session: AsyncSession,
    item_id: int,
    payload: WatchlistItemUpdate,
    user_key: str = DEFAULT_USER_KEY,
) -> WatchlistItemRead | None:
    user = await get_or_create_user(session, user_key)
    item = await _get_watchlist_item(session, user.id, item_id)
    if item is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(item, field_name, value)

    await session.commit()
    await session.refresh(item)
    return _watchlist_read(item, user.user_key)


async def delete_watchlist_item(
    session: AsyncSession,
    item_id: int,
    user_key: str = DEFAULT_USER_KEY,
) -> bool:
    user = await get_or_create_user(session, user_key)
    item = await _get_watchlist_item(session, user.id, item_id)
    if item is None:
        return False

    await session.delete(item)
    await session.commit()
    return True


async def _get_user(session: AsyncSession, user_key: str) -> UserProfile | None:
    statement = select(UserProfile).where(UserProfile.user_key == user_key)
    return await session.scalar(statement)


async def _find_holding(
    session: AsyncSession,
    user_id: int,
    market: str,
    instrument_code: str,
) -> PortfolioHolding | None:
    statement = select(PortfolioHolding).where(
        PortfolioHolding.user_id == user_id,
        PortfolioHolding.market == market,
        PortfolioHolding.instrument_code == instrument_code,
    )
    return await session.scalar(statement)


async def _get_holding(
    session: AsyncSession,
    user_id: int,
    holding_id: int,
) -> PortfolioHolding | None:
    statement = select(PortfolioHolding).where(
        PortfolioHolding.id == holding_id,
        PortfolioHolding.user_id == user_id,
    )
    return await session.scalar(statement)


async def _find_watchlist_item(
    session: AsyncSession,
    user_id: int,
    market: str,
    instrument_code: str,
) -> WatchlistItem | None:
    statement = select(WatchlistItem).where(
        WatchlistItem.user_id == user_id,
        WatchlistItem.market == market,
        WatchlistItem.instrument_code == instrument_code,
    )
    return await session.scalar(statement)


async def _get_watchlist_item(
    session: AsyncSession,
    user_id: int,
    item_id: int,
) -> WatchlistItem | None:
    statement = select(WatchlistItem).where(
        WatchlistItem.id == item_id,
        WatchlistItem.user_id == user_id,
    )
    return await session.scalar(statement)


def _holding_read(holding: PortfolioHolding, user_key: str) -> HoldingRead:
    return HoldingRead(
        id=holding.id,
        user_key=user_key,
        instrument_code=holding.instrument_code,
        instrument_name=holding.instrument_name,
        market=holding.market,
        note=holding.note,
        cost_price=holding.cost_price,
        position_ratio=holding.position_ratio,
        alert_enabled=holding.alert_enabled,
        created_at=holding.created_at,
        updated_at=holding.updated_at,
    )


def _watchlist_read(item: WatchlistItem, user_key: str) -> WatchlistItemRead:
    return WatchlistItemRead(
        id=item.id,
        user_key=user_key,
        instrument_code=item.instrument_code,
        instrument_name=item.instrument_name,
        market=item.market,
        note=item.note,
        alert_enabled=item.alert_enabled,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _normalize_user_key(user_key: str) -> str:
    normalized = user_key.strip()
    return normalized or DEFAULT_USER_KEY
