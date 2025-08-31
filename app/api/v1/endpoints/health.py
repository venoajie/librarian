# app\api\v1\endpoints\health.py

import psutil
from fastapi import APIRouter, Request
from app.models.schemas import HealthResponse, HealthStatus, IndexStatus, ResourceUsage
from app.core.config import settings

router = APIRouter()

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Health Check",
    tags=["Monitoring"]
)
async def health_check(request: Request):
    """
    Provides the current operational status of the Librarian service,
    including index status and resource utilization.
    """
    # Read state from the central app object, not a local global
    index_status = request.app.state.index_status
    index_last_modified = request.app.state.index_last_modified
    
    overall_status = HealthStatus.OK if index_status == IndexStatus.LOADED else HealthStatus.DEGRADED
    
    cpu_load = psutil.cpu_percent(interval=None)
    memory_info = psutil.virtual_memory()
    
    return HealthResponse(
        status=overall_status,
        version=settings.SERVICE_VERSION,
        index_status=index_status,
        index_last_modified=index_last_modified,
        resource_usage=ResourceUsage(
            cpu_load_percent=cpu_load,
            memory_usage_percent=memory_info.percent
        )
    )