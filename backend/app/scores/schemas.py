from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ScoreStatus(StrEnum):
    GENERATED = "generated"
    PENDING_WINDOW = "pending_window"


class ScoreRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    signal_id: int
    window_days: int
    score_status: ScoreStatus
    composite_score: float
    components: dict[str, object]
    details: dict[str, object]
    evaluated_at: datetime
    created_at: datetime


class ScoreRunRead(BaseModel):
    signal_id: int
    records: list[ScoreRecordRead]
