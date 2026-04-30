from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.providers.akshare import AKSHARE_ENDPOINTS, list_akshare_endpoints
from app.providers.schemas import (
    AkshareCollectionResponse,
    ProviderCollectionStatusResponse,
    ProviderEndpointInfo,
    ProviderFetchLogRead,
    ProviderSnapshotSummary,
)
from app.providers.service import (
    collect_minimal_akshare,
    get_akshare_collection_status,
    list_latest_provider_snapshots,
    list_provider_fetch_logs,
)

router = APIRouter(prefix="/providers", tags=["providers"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]


@router.get("/akshare/endpoints", response_model=list[ProviderEndpointInfo])
async def akshare_endpoints() -> list[ProviderEndpointInfo]:
    return list_akshare_endpoints()


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


def _ensure_known_akshare_endpoint(endpoint: str | None) -> None:
    if endpoint is not None and endpoint not in AKSHARE_ENDPOINTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown akshare endpoint: {endpoint}",
        )


def _database_unavailable(action: str, exc: SQLAlchemyError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"database unavailable while {action}: {exc.__class__.__name__}",
    )
