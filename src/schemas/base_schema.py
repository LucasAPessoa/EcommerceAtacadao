from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TimestampMixinSchema(BaseModel):
    created_at: datetime
    updated_at: datetime

class SoftDeleteMixinSchema(TimestampMixinSchema):
    deleted_at: Optional[datetime] = None