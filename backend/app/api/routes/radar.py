from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.radar.schemas import RadarPriority, RadarScanRead, RadarSignalDetail, RadarSignalRead
from app.radar.service import (
    get_latest_radar_scan,
    get_radar_signal_detail,
    list_radar_signals,
    run_radar_scan,
)

router = APIRouter(prefix="/radar", tags=["radar"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]


@router.post("/scans/run", response_model=RadarScanRead)
async def run_scan(session: SessionDep) -> RadarScanRead:
    try:
        return await run_radar_scan(session)
    except SQLAlchemyError as exc:
        raise _database_unavailable("running radar scan", exc) from exc


@router.get("/scans/latest", response_model=RadarScanRead)
async def latest_scan(session: SessionDep) -> RadarScanRead:
    try:
        scan = await get_latest_radar_scan(session)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading latest radar scan", exc) from exc

    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no radar scan has been created",
        )

    return scan


@router.get("/signals", response_model=list[RadarSignalRead])
async def signals(
    session: SessionDep,
    priority: RadarPriority | None = None,
    limit: LimitQuery = 50,
) -> list[RadarSignalRead]:
    try:
        return await list_radar_signals(session, priority=priority, limit=limit)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading radar signals", exc) from exc


@router.get("/signals/{signal_id}", response_model=RadarSignalDetail)
async def signal_detail(session: SessionDep, signal_id: int) -> RadarSignalDetail:
    try:
        signal = await get_radar_signal_detail(session, signal_id)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading radar signal", exc) from exc

    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"radar signal not found: {signal_id}",
        )

    return signal


def _database_unavailable(action: str, exc: SQLAlchemyError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"database unavailable while {action}: {exc.__class__.__name__}",
    )
