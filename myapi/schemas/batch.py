from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class BatchJobResult(BaseModel):
    job: str
    status: Literal["queued", "failed"]
    sequence: Optional[int] = None
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BatchQueueResponse(BaseModel):
    message: str
    current_time: Optional[str] = None
    details: List[BatchJobResult] = Field(default_factory=list)


class QueueStatus(BaseModel):
    queue_url: str
    approximate_number_of_messages: Optional[str] = None
    approximate_number_of_messages_not_visible: Optional[str] = None
    approximate_number_of_messages_delayed: Optional[str] = None
    created_timestamp: Optional[str] = None
    last_modified_timestamp: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


class BatchScheduleInfo(BaseModel):
    morning_batch_time: str
    evening_batch_time: str
    next_morning_batch: str
    next_evening_batch: str


class BatchJobsStatusResponse(BaseModel):
    current_time: str
    queue_status: QueueStatus
    batch_schedule_info: BatchScheduleInfo
    status: str

