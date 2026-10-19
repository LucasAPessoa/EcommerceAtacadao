from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BlingCompanySchema(BaseModel):
    id: str
    name: Optional[str] = None


class BlingLastErrorSchema(BaseModel):
    code: str
    at: Optional[datetime] = None


class BlingEventSchema(BaseModel):
    event: str
    reason: Optional[str] = None
    at: datetime


class BlingStatusResponse(BaseModel):
    """Estado da conexão. Nunca inclui tokens."""

    status: str
    company: Optional[BlingCompanySchema] = None
    connected_at: Optional[datetime] = None
    last_refreshed_at: Optional[datetime] = None
    last_error: Optional[BlingLastErrorSchema] = None
    recent_events: list[BlingEventSchema] = []
