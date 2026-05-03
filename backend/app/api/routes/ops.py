from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.ops.schemas import OpsHistoryRead, OpsOverviewRead
from app.ops.service import get_ops_history, get_ops_overview

router = APIRouter(prefix="/ops", tags=["ops"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
LookbackHoursQuery = Annotated[int, Query(ge=1, le=168)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]


@router.get("/overview", response_model=OpsOverviewRead)
async def ops_overview(
    session: SessionDep,
    lookback_hours: LookbackHoursQuery = 24,
) -> OpsOverviewRead:
    try:
        return await get_ops_overview(session, lookback_hours=lookback_hours)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"database unavailable while reading ops overview: {exc.__class__.__name__}",
        ) from exc


@router.get("/history", response_model=OpsHistoryRead)
async def ops_history(
    session: SessionDep,
    lookback_hours: LookbackHoursQuery = 24,
    limit: LimitQuery = 30,
) -> OpsHistoryRead:
    try:
        return await get_ops_history(
            session,
            lookback_hours=lookback_hours,
            limit=limit,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"database unavailable while reading ops history: {exc.__class__.__name__}",
        ) from exc
