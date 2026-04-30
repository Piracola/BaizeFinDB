from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.governance.review import list_radar_signal_reviews, review_radar_signal
from app.governance.share import get_radar_signal_share_preview
from app.radar.schemas import (
    RadarOverviewRead,
    RadarPriority,
    RadarScanRead,
    RadarSignalDetail,
    RadarSignalPublicShareRead,
    RadarSignalRead,
    RadarSignalReviewRead,
    RadarSignalSharePreviewRead,
    RadarSignalShareStatus,
)
from app.radar.service import (
    get_latest_radar_scan,
    get_radar_overview,
    get_radar_scan,
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


@router.get("/scans/{scan_id}", response_model=RadarScanRead)
async def scan_detail(session: SessionDep, scan_id: int) -> RadarScanRead:
    try:
        scan = await get_radar_scan(session, scan_id)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading radar scan", exc) from exc

    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"radar scan not found: {scan_id}",
        )

    return scan


@router.get("/overview", response_model=RadarOverviewRead)
async def overview(
    session: SessionDep,
    limit: LimitQuery = 50,
) -> RadarOverviewRead:
    try:
        return await get_radar_overview(session, limit=limit)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading radar overview", exc) from exc


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


@router.post("/signals/{signal_id}/review", response_model=RadarSignalReviewRead)
async def review_signal(session: SessionDep, signal_id: int) -> RadarSignalReviewRead:
    try:
        review = await review_radar_signal(session, signal_id)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reviewing radar signal", exc) from exc

    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"radar signal not found: {signal_id}",
        )

    return review


@router.get("/signals/{signal_id}/reviews", response_model=list[RadarSignalReviewRead])
async def signal_reviews(session: SessionDep, signal_id: int) -> list[RadarSignalReviewRead]:
    try:
        reviews = await list_radar_signal_reviews(session, signal_id)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading radar signal reviews", exc) from exc

    if reviews is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"radar signal not found: {signal_id}",
        )

    return reviews


@router.get("/signals/{signal_id}/share-preview", response_model=RadarSignalSharePreviewRead)
async def signal_share_preview(
    session: SessionDep,
    signal_id: int,
) -> RadarSignalSharePreviewRead:
    try:
        preview = await get_radar_signal_share_preview(session, signal_id)
    except SQLAlchemyError as exc:
        raise _database_unavailable("building radar signal share preview", exc) from exc

    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"radar signal not found: {signal_id}",
        )

    return preview


@router.get("/signals/{signal_id}/share-payload", response_model=RadarSignalPublicShareRead)
async def signal_share_payload(
    session: SessionDep,
    signal_id: int,
) -> RadarSignalPublicShareRead:
    try:
        preview = await get_radar_signal_share_preview(session, signal_id)
    except SQLAlchemyError as exc:
        raise _database_unavailable("building radar signal share payload", exc) from exc

    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"radar signal not found: {signal_id}",
        )

    if preview.share_status != RadarSignalShareStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="radar signal is not shareable; use internal share-preview preflight",
        )

    return preview.public_payload


def _database_unavailable(action: str, exc: SQLAlchemyError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"database unavailable while {action}: {exc.__class__.__name__}",
    )
