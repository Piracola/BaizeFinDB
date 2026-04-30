from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.providers.akshare import list_akshare_endpoints
from app.providers.schemas import AkshareCollectionResponse, ProviderEndpointInfo
from app.providers.service import collect_minimal_akshare

router = APIRouter(prefix="/providers", tags=["providers"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"database unavailable while recording provider fetch: {exc.__class__.__name__}",
        ) from exc
