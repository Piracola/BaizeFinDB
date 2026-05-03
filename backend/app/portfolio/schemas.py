from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

DEFAULT_USER_KEY = "default"

InstrumentCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]
InstrumentName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
Market = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
UserKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class HoldingCreate(BaseModel):
    instrument_code: InstrumentCode
    instrument_name: InstrumentName
    market: Market = "A_SHARE"
    note: Note = ""
    cost_price: float | None = Field(default=None, ge=0)
    position_ratio: float | None = Field(default=None, ge=0, le=1)
    alert_enabled: bool = True

    @field_validator("instrument_code", "market")
    @classmethod
    def uppercase_identity_fields(cls, value: str) -> str:
        return value.upper()


class HoldingUpdate(BaseModel):
    instrument_name: InstrumentName | None = None
    note: Note | None = None
    cost_price: float | None = Field(default=None, ge=0)
    position_ratio: float | None = Field(default=None, ge=0, le=1)
    alert_enabled: bool | None = None


class HoldingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_key: str
    instrument_code: str
    instrument_name: str
    market: str
    note: str
    cost_price: float | None
    position_ratio: float | None
    alert_enabled: bool
    created_at: datetime
    updated_at: datetime


class WatchlistItemCreate(BaseModel):
    instrument_code: InstrumentCode
    instrument_name: InstrumentName
    market: Market = "A_SHARE"
    note: Note = ""
    alert_enabled: bool = True

    @field_validator("instrument_code", "market")
    @classmethod
    def uppercase_identity_fields(cls, value: str) -> str:
        return value.upper()


class WatchlistItemUpdate(BaseModel):
    instrument_name: InstrumentName | None = None
    note: Note | None = None
    alert_enabled: bool | None = None


class WatchlistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_key: str
    instrument_code: str
    instrument_name: str
    market: str
    note: str
    alert_enabled: bool
    created_at: datetime
    updated_at: datetime
