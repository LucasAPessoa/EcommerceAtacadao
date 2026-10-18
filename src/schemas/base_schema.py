from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TimestampMixinSchema(BaseModel):
    created_at: datetime
    updated_at: datetime

class SoftDeleteMixinSchema(TimestampMixinSchema):
    deleted_at: Optional[datetime] = None