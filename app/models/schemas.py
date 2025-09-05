# app\models\schemas.py

from typing import List, Optional, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum

class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"

class IndexStatus(str, Enum):
    LOADED = "loaded"
    LOADING = "loading"
    NOT_FOUND = "not_found"

class ResourceUsage(BaseModel):
    cpu_load_percent: float = Field(..., description="Current system-wide CPU load in percent.")
    memory_usage_percent: float = Field(..., description="Current system-wide memory usage in percent.")
    
class HealthResponse(BaseModel):
    """Health check response model."""
    status: HealthStatus
    version: str
    index_status: IndexStatus
    db_status: str = Field("unknown", description="Connection status to PostgreSQL database ('connected' or 'disconnected').")
    redis_status: str = Field("unknown", description="Connection status to Redis cache ('connected' or 'disconnected').")
    reranker_status: str = Field("unknown", description="Status of the reranker model ('loaded', 'error', 'disabled').")
    index_last_modified: Optional[datetime] = None
    resource_usage: ResourceUsage
    index_branch: Optional[str] = Field(None, description="The git branch of the loaded index.")
    db_table_name: Optional[str] = Field(None, description="The name of the active PostgreSQL table.")

class ContextRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=512, description="The user query.")
    max_results: int = Field(5, gt=0, le=20, description="Max number of results.")
    filters: Optional[dict[str, Any]] = Field(None, description="Key-value pairs to filter metadata. Example: {'language': 'python', 'is_test_file': false}")

    @validator("query")
    def query_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty or just whitespace")
        return v

class ContextChunk(BaseModel):
    content: str
    metadata: dict[str, Any]
    score: float

class ContextResponse(BaseModel):
    query_id: str
    context: List[ContextChunk]
    processing_time_ms: int