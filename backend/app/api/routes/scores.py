from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.scores.schemas import ScoreRunRead
from app.scores.service import generate_signal_scores, list_signal_scores

router = APIRouter(prefix="/scores", tags=["scores"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/signals/{signal_id}", response_model=ScoreRunRead)
async def score_signal(
    signal_id: int,
    session: SessionDep,
) -> ScoreRunRead:
    try:
        result = await generate_signal_scores(session, signal_id)
    except SQLAlchemyError as exc:
        raise _database_unavailable("generating signal scores", exc) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"radar signal not found: {signal_id}",
        )

    return result


@router.get("/signals/{signal_id}", response_model=ScoreRunRead)
async def signal_scores(
    signal_id: int,
    session: SessionDep,
) -> ScoreRunRead:
    try:
        result = await list_signal_scores(session, signal_id)
    except SQLAlchemyError as exc:
        raise _database_unavailable("reading signal scores", exc) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"radar signal not found: {signal_id}",
        )

    return result


def _database_unavailable(action: str, exc: SQLAlchemyError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"database unavailable while {action}: {exc.__class__.__name__}",
    )
