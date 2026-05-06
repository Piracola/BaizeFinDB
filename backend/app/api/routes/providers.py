from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.providers.akshare import AKSHARE_ENDPOINTS, list_akshare_endpoints
from app.providers.schemas import (
    AkshareCollectionResponse,
    ProviderCollectionStatusResponse,
    ProviderEndpointInfo,
    ProviderEndpointResult,
    ProviderFetchLogRead,
    ProviderSnapshotSummary,
    TushareEndpointInfo,
    TushareProviderStatusResponse,
    TushareReadinessResponse,
)
from app.providers.service import (
    collect_minimal_akshare,
    collect_tushare_announcements,
    collect_tushare_daily,
    collect_tushare_stock_basic,
    collect_tushare_stock_company,
    get_akshare_collection_status,
    get_tushare_readiness,
    list_latest_provider_snapshots,
    list_provider_fetch_logs,
)
from app.providers.tushare import (
    TUSHARE_ENDPOINTS,
    get_tushare_provider_status,
    list_tushare_endpoints,
)

router = APIRouter(prefix="/providers", tags=["providers"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]
TushareDateQuery = Annotated[str | None, Query(pattern=r"^\d{8}$")]
TushareExchangeQuery = Annotated[Literal["SSE", "SZSE", "BSE"], Query()]
TushareTsCodeQuery = Annotated[
    str | None,
    Query(pattern=r"^\d{6}\.(?:SH|SZ|BJ)(?:,\d{6}\.(?:SH|SZ|BJ))*$"),
]


@router.get("/akshare/endpoints", response_model=list[ProviderEndpointInfo])
async def akshare_endpoints() -> list[ProviderEndpointInfo]:
    return list_akshare_endpoints()


@router.get("/tushare/endpoints", response_model=list[TushareEndpointInfo])
async def tushare_endpoints() -> list[TushareEndpointInfo]:
    return list_tushare_endpoints()


@router.get("/tushare/status", response_model=TushareProviderStatusResponse)
async def tushare_provider_status() -> TushareProviderStatusResponse:
    return get_tushare_provider_status()


@router.get("/tushare/readiness", response_model=TushareReadinessResponse)
async def tushare_readiness(
    session: SessionDep,
) -> TushareReadinessResponse:
    try:
        return await get_tushare_readiness(session)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading tushare readiness", exc) from exc


@router.post("/tushare/fetch/stock-basic", response_model=ProviderEndpointResult)
async def fetch_tushare_stock_basic(
    session: SessionDep,
) -> ProviderEndpointResult:
    try:
        return await collect_tushare_stock_basic(session)
    except SQLAlchemyError as exc:
        raise _database_unavailable("recording tushare fetch", exc) from exc


@router.post("/tushare/fetch/daily", response_model=ProviderEndpointResult)
async def fetch_tushare_daily(
    session: SessionDep,
    trade_date: TushareDateQuery = None,
    ts_code: TushareTsCodeQuery = None,
    start_date: TushareDateQuery = None,
    end_date: TushareDateQuery = None,
) -> ProviderEndpointResult:
    _ensure_valid_tushare_daily_query(
        trade_date=trade_date,
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
    )

    try:
        return await collect_tushare_daily(
            session,
            trade_date=trade_date,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable("recording tushare daily fetch", exc) from exc


@router.post("/tushare/fetch/announcements", response_model=ProviderEndpointResult)
async def fetch_tushare_announcements(
    session: SessionDep,
    ann_date: TushareDateQuery = None,
) -> ProviderEndpointResult:
    try:
        return await collect_tushare_announcements(session, ann_date=ann_date)
    except SQLAlchemyError as exc:
        raise _database_unavailable("recording tushare announcements fetch", exc) from exc


@router.post("/tushare/fetch/stock-company", response_model=ProviderEndpointResult)
async def fetch_tushare_stock_company(
    session: SessionDep,
    exchange: TushareExchangeQuery = "SZSE",
) -> ProviderEndpointResult:
    try:
        return await collect_tushare_stock_company(session, exchange=exchange)
    except SQLAlchemyError as exc:
        raise _database_unavailable("recording tushare stock company fetch", exc) from exc


@router.post("/akshare/fetch/minimal", response_model=AkshareCollectionResponse)
async def fetch_minimal_akshare(
    session: SessionDep,
) -> AkshareCollectionResponse:
    try:
        return await collect_minimal_akshare(session)
    except SQLAlchemyError as exc:
        raise _database_unavailable("recording provider fetch", exc) from exc


@router.get("/akshare/status", response_model=ProviderCollectionStatusResponse)
async def akshare_collection_status(
    session: SessionDep,
) -> ProviderCollectionStatusResponse:
    try:
        return await get_akshare_collection_status(session)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading provider status", exc) from exc


@router.get("/akshare/fetch-logs", response_model=list[ProviderFetchLogRead])
async def akshare_fetch_logs(
    session: SessionDep,
    endpoint: str | None = None,
    limit: LimitQuery = 20,
) -> list[ProviderFetchLogRead]:
    _ensure_known_akshare_endpoint(endpoint)

    try:
        return await list_provider_fetch_logs(
            session,
            provider_name="akshare",
            endpoint=endpoint,
            limit=limit,
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading provider fetch logs", exc) from exc


@router.get("/tushare/fetch-logs", response_model=list[ProviderFetchLogRead])
async def tushare_fetch_logs(
    session: SessionDep,
    endpoint: str | None = None,
    limit: LimitQuery = 20,
) -> list[ProviderFetchLogRead]:
    _ensure_known_tushare_endpoint(endpoint)

    try:
        return await list_provider_fetch_logs(
            session,
            provider_name="tushare",
            endpoint=endpoint,
            limit=limit,
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading tushare fetch logs", exc) from exc


@router.get("/akshare/snapshots/latest", response_model=list[ProviderSnapshotSummary])
async def akshare_latest_snapshots(
    session: SessionDep,
    endpoint: str | None = None,
) -> list[ProviderSnapshotSummary]:
    _ensure_known_akshare_endpoint(endpoint)

    try:
        return await list_latest_provider_snapshots(
            session,
            provider_name="akshare",
            endpoint=endpoint,
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading provider snapshots", exc) from exc


@router.get("/tushare/snapshots/latest", response_model=list[ProviderSnapshotSummary])
async def tushare_latest_snapshots(
    session: SessionDep,
    endpoint: str | None = None,
) -> list[ProviderSnapshotSummary]:
    _ensure_known_tushare_endpoint(endpoint)

    try:
        return await list_latest_provider_snapshots(
            session,
            provider_name="tushare",
            endpoint=endpoint,
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading tushare snapshots", exc) from exc


def _ensure_known_akshare_endpoint(endpoint: str | None) -> None:
    if endpoint is not None and endpoint not in AKSHARE_ENDPOINTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown akshare endpoint: {endpoint}",
        )


def _ensure_known_tushare_endpoint(endpoint: str | None) -> None:
    if endpoint is not None and endpoint not in TUSHARE_ENDPOINTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown tushare endpoint: {endpoint}",
        )


def _ensure_valid_tushare_daily_query(
    *,
    trade_date: str | None,
    ts_code: str | None,
    start_date: str | None,
    end_date: str | None,
) -> None:
    if trade_date is not None and (start_date is not None or end_date is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="trade_date cannot be combined with start_date/end_date.",
        )

    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date and end_date must be provided together.",
        )

    if ts_code is None and (start_date is not None or end_date is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ts_code is required when using start_date/end_date.",
        )


def _database_unavailable(action: str, exc: SQLAlchemyError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"database unavailable while {action}: {exc.__class__.__name__}",
    )
