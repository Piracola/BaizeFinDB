from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.portfolio.schemas import DEFAULT_USER_KEY
from app.reports.schemas import (
    CreatableReportType,
    PeriodicReportRead,
    PeriodicReportType,
    ReportRead,
    SignalReportCreate,
)
from app.reports.service import (
    ReportBlockedError,
    create_signal_report,
    generate_periodic_report,
    get_report,
    list_reports,
)

router = APIRouter(prefix="/reports", tags=["reports"])
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


@router.post("/from-signal", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report_from_signal(
    payload: SignalReportCreate,
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> ReportRead:
    try:
        report = await create_signal_report(
            session,
            signal_id=payload.signal_id,
            report_type=payload.report_type,
            user_key=user_key,
        )
    except ReportBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "signal review blocked report generation",
                "reasons": exc.reasons,
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable("creating report", exc) from exc

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"radar signal not found: {payload.signal_id}",
        )

    return report


@router.get("", response_model=list[ReportRead])
async def reports(
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
    report_type: CreatableReportType | None = None,
    limit: LimitQuery = 50,
) -> list[ReportRead]:
    try:
        return await list_reports(
            session,
            user_key=user_key,
            report_type=report_type,
            limit=limit,
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading reports", exc) from exc


@router.get("/periodic", response_model=PeriodicReportRead)
async def periodic_report(
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
    period: PeriodicReportType = PeriodicReportType.DAILY,
) -> PeriodicReportRead:
    try:
        return await generate_periodic_report(
            session,
            report_type=period,
            user_key=user_key,
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable("generating periodic report", exc) from exc


@router.get("/{report_id}", response_model=ReportRead)
async def report_detail(
    report_id: int,
    session: SessionDep,
    user_key: UserKeyQuery = DEFAULT_USER_KEY,
) -> ReportRead:
    try:
        report = await get_report(session, report_id, user_key=user_key)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading report", exc) from exc

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"report not found: {report_id}",
        )

    return report


def _database_unavailable(action: str, exc: SQLAlchemyError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"database unavailable while {action}: {exc.__class__.__name__}",
    )
