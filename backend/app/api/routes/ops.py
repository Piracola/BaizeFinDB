from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.ops.schemas import OpsOverviewRead
from app.ops.service import get_ops_overview

router = APIRouter(prefix="/ops", tags=["ops"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
LookbackHoursQuery = Annotated[int, Query(ge=1, le=168)]


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
