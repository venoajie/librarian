# app\api\v1\endpoints\health.py

import logging
import psutil
from fastapi import APIRouter, Request

from app.models.schemas import HealthResponse, HealthStatus, IndexStatus, ResourceUsage

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Get Service Health",
    tags=["Monitoring"]
)
async def get_health(request: Request):
    """
    Provides a detailed health status of the service.

    - `status`: "ok" only if the index is fully loaded. Otherwise "degraded".
    - `index_status`: The current state of the ChromaDB index (loading, loaded, not_found).
    - `resource_usage`: System metrics. A failure to collect these metrics will be logged
      but will NOT cause the health check to fail.
    """
    app_state = request.app.state
    index_status = getattr(app_state, 'index_status', IndexStatus.LOADING)
    
    # The primary determinant of health is whether the index is loaded.
    status = HealthStatus.OK if index_status == IndexStatus.LOADED else HealthStatus.DEGRADED

    resource_usage: ResourceUsage
    try:
        # Attempt to get resource usage, but do not let this fail the health check.
        cpu_load = psutil.cpu_percent(interval=None)
        memory_info = psutil.virtual_memory()
        resource_usage = ResourceUsage(
            cpu_load_percent=cpu_load,
            memory_usage_percent=memory_info.percent
        )
    except Exception as e:
        # If psutil fails (e.g., due to container environment restrictions),
        # log the error and return zeroed-out metrics. This is a non-fatal error.
        logger.warning(f"Could not retrieve resource usage: {e}. This is non-fatal.")
        resource_usage = ResourceUsage(cpu_load_percent=0.0, memory_usage_percent=0.0)

    return HealthResponse(
        status=status,
        version=getattr(app_state, 'settings', {}).get('SERVICE_VERSION', '1.0.0'),
        index_status=index_status,
        index_last_modified=getattr(app_state, 'index_last_modified', None),
        resource_usage=resource_usage
    )
