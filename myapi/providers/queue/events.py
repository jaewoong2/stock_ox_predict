
from pydantic import BaseModel
from typing import List

class EODFetchEvent(BaseModel):
    trading_day: str
    symbols: List[str]
    provider: str
    retry_count: int = 0

class SettlementComputeEvent(BaseModel):
    trading_day: str
    trigger_source: str

class PointsAwardEvent(BaseModel):
    user_id: int
    trading_day: str
    deduplication_id: str
