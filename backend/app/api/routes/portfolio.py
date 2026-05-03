from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.portfolio.schemas import (
    DEFAULT_USER_KEY,
    HoldingCreate,
    HoldingRead,
    HoldingUpdate,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistItemUpdate,
)
from app.portfolio.service import (
    DuplicatePortfolioItemError,
    create_holding,
    create_watchlist_item,
    delete_holding,
    delete_watchlist_item,
    list_holdings,
    list_watchlist_items,
    update_holding,
    update_watchlist_item,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
UserKeyQuery = Annotated[
    str,
    Query(
        min_length=1,
        max_length=120,
        description="Single-user MVP isolation key",
    ),
]


@router.get("/holdings", response_model=list[HoldingRead])
async def holdings(
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> list[HoldingRead]:
    try:
        return await list_holdings(session, user_key=user_key)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading holdings", exc) from exc


@router.post("/holdings", response_model=HoldingRead, status_code=status.HTTP_201_CREATED)
async def add_holding(
    payload: HoldingCreate,
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> HoldingRead:
    try:
        return await create_holding(session, payload, user_key=user_key)
    except DuplicatePortfolioItemError as exc:
        raise _duplicate_item("holding", exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable("creating holding", exc) from exc


@router.patch("/holdings/{holding_id}", response_model=HoldingRead)
async def edit_holding(
    holding_id: int,
    payload: HoldingUpdate,
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> HoldingRead:
    try:
        holding = await update_holding(session, holding_id, payload, user_key=user_key)
    except SQLAlchemyError as exc:
        raise _database_unavailable("updating holding", exc) from exc

    if holding is None:
        raise _not_found("holding", holding_id)

    return holding


@router.delete("/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_holding(
    holding_id: int,
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> Response:
    try:
        deleted = await delete_holding(session, holding_id, user_key=user_key)
    except SQLAlchemyError as exc:
        raise _database_unavailable("deleting holding", exc) from exc

    if not deleted:
        raise _not_found("holding", holding_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/watchlist", response_model=list[WatchlistItemRead])
async def watchlist(
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> list[WatchlistItemRead]:
    try:
        return await list_watchlist_items(session, user_key=user_key)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading watchlist", exc) from exc


@router.post("/watchlist", response_model=WatchlistItemRead, status_code=status.HTTP_201_CREATED)
async def add_watchlist_item(
    payload: WatchlistItemCreate,
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> WatchlistItemRead:
    try:
        return await create_watchlist_item(session, payload, user_key=user_key)
    except DuplicatePortfolioItemError as exc:
        raise _duplicate_item("watchlist item", exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable("creating watchlist item", exc) from exc


@router.patch("/watchlist/{item_id}", response_model=WatchlistItemRead)
async def edit_watchlist_item(
    item_id: int,
    payload: WatchlistItemUpdate,
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> WatchlistItemRead:
    try:
        item = await update_watchlist_item(session, item_id, payload, user_key=user_key)
    except SQLAlchemyError as exc:
        raise _database_unavailable("updating watchlist item", exc) from exc

    if item is None:
        raise _not_found("watchlist item", item_id)

    return item


@router.delete("/watchlist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_watchlist_item(
    item_id: int,
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> Response:
    try:
        deleted = await delete_watchlist_item(session, item_id, user_key=user_key)
    except SQLAlchemyError as exc:
        raise _database_unavailable("deleting watchlist item", exc) from exc

    if not deleted:
        raise _not_found("watchlist item", item_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _duplicate_item(item_type: str, exc: DuplicatePortfolioItemError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"{item_type} already exists: {exc}",
    )


def _not_found(item_type: str, item_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{item_type} not found: {item_id}",
    )


def _database_unavailable(action: str, exc: SQLAlchemyError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"database unavailable while {action}: {exc.__class__.__name__}",
    )
